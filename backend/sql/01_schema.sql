-- =====================================================================================
--  Hospital Appointment Booking System — canonical schema (MySQL 8.0, InnoDB, utf8mb4)
--
--  Run with:  python -m scripts.init_db          (from the backend/ directory)
--  Or by hand: mysql -u root -p appointment_db < sql/01_schema.sql
--
--  All DATETIME columns hold naive UTC. See backend/app/core/timeutil.py.
-- =====================================================================================

-- -------------------------------------------------------------------------------------
-- users — one table for both roles, discriminated by `role`.
-- -------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  full_name      VARCHAR(120)  NOT NULL,
  email          VARCHAR(255)  NOT NULL,
  password_hash  VARCHAR(255)  NOT NULL,
  role           ENUM('DOCTOR','PATIENT') NOT NULL,
  specialization VARCHAR(120)  NULL COMMENT 'Doctors only',
  phone          VARCHAR(32)   NULL,
  created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------------------------------
-- services — what a doctor offers. A slot may optionally point at one.
-- -------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS services (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  doctor_id        BIGINT UNSIGNED NOT NULL,
  name             VARCHAR(120) NOT NULL,
  description      VARCHAR(500) NULL,
  duration_minutes INT NOT NULL,
  price            DECIMAL(10,2) NOT NULL DEFAULT 0.00,
  is_active        TINYINT(1) NOT NULL DEFAULT 1,
  created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_services_doctor_name (doctor_id, name),
  KEY ix_services_doctor (doctor_id, is_active),
  CONSTRAINT fk_services_doctor FOREIGN KEY (doctor_id)
    REFERENCES users (id) ON DELETE CASCADE,
  CONSTRAINT ck_services_duration CHECK (duration_minutes BETWEEN 5 AND 480),
  CONSTRAINT ck_services_price CHECK (price >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------------------------------
-- slots — a bookable window in one doctor's calendar.
--
-- `status` is kept in lockstep with the appointments table by the service layer, always
-- inside the same transaction:
--     OPEN      -> no occupying appointment
--     BOOKED    -> exactly one appointment with status BOOKED
--     COMPLETED -> exactly one appointment with status COMPLETED (stays unbookable)
-- -------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS slots (
  id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  doctor_id  BIGINT UNSIGNED NOT NULL,
  service_id BIGINT UNSIGNED NULL,
  start_at   DATETIME NOT NULL COMMENT 'UTC',
  end_at     DATETIME NOT NULL COMMENT 'UTC',
  status     ENUM('OPEN','BOOKED','COMPLETED') NOT NULL DEFAULT 'OPEN',
  notes      VARCHAR(500) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_slots_doctor_start (doctor_id, start_at),
  KEY ix_slots_open_browse (status, start_at),
  KEY ix_slots_service (service_id),
  CONSTRAINT fk_slots_doctor FOREIGN KEY (doctor_id)
    REFERENCES users (id) ON DELETE CASCADE,
  CONSTRAINT fk_slots_service FOREIGN KEY (service_id)
    REFERENCES services (id) ON DELETE SET NULL,
  CONSTRAINT ck_slots_time CHECK (end_at > start_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------------------------------
-- appointments — a patient's claim on a slot.
--
-- ►►► BUSINESS RULE 1 IS ENFORCED HERE, BY THE DATABASE ITSELF ◄◄◄
--
-- "A slot can hold at most one booked appointment at a time."
--
-- We cannot use UNIQUE (slot_id): that would also block re-booking a slot after a
-- cancellation, which rule 3 requires. MySQL has no partial/filtered indexes either.
-- So we project the predicate "does this row occupy its slot?" into a generated column
-- and put a plain UNIQUE index on that. A UNIQUE index ignores NULLs, giving exactly:
--
--     at most ONE live (BOOKED/COMPLETED) appointment per slot
--     unlimited CANCELLED rows per slot, so a released slot is re-bookable
--
-- The column MUST be VIRTUAL, not STORED. With STORED, this CREATE TABLE fails:
--     ERROR 1215 (HY000): Cannot add foreign key constraint
-- because MySQL forbids ON DELETE CASCADE / SET NULL / SET DEFAULT on the *base column*
-- of a STORED generated column, and slot_id is the base column. InnoDB indexes virtual
-- columns fine, so the guarantee is identical. Verified on MySQL 8.0.44.
-- -------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS appointments (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  slot_id       BIGINT UNSIGNED NOT NULL,
  patient_id    BIGINT UNSIGNED NOT NULL,
  doctor_id     BIGINT UNSIGNED NOT NULL
                COMMENT 'Denormalised from slots.doctor_id: authz filter + stable history',
  status        ENUM('BOOKED','CANCELLED','COMPLETED') NOT NULL DEFAULT 'BOOKED',
  reason        VARCHAR(500)  NULL COMMENT 'Written by the patient at booking',
  doctor_notes  VARCHAR(1000) NULL COMMENT 'Written by the doctor at completion',
  cancelled_by  ENUM('PATIENT','DOCTOR') NULL,
  cancel_reason VARCHAR(500) NULL,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  cancelled_at  DATETIME NULL,
  completed_at  DATETIME NULL,

  occupies_slot_id BIGINT UNSIGNED
    GENERATED ALWAYS AS (IF(status IN ('BOOKED','COMPLETED'), slot_id, NULL)) VIRTUAL,

  PRIMARY KEY (id),
  UNIQUE KEY uq_appointments_occupied_slot (occupies_slot_id),
  KEY ix_appointments_patient (patient_id, status),
  KEY ix_appointments_doctor (doctor_id, status),
  KEY ix_appointments_slot (slot_id),
  CONSTRAINT fk_appt_slot FOREIGN KEY (slot_id)
    REFERENCES slots (id) ON DELETE CASCADE,
  CONSTRAINT fk_appt_patient FOREIGN KEY (patient_id)
    REFERENCES users (id) ON DELETE CASCADE,
  CONSTRAINT fk_appt_doctor FOREIGN KEY (doctor_id)
    REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------------------------------
-- slot_waitlist — the FIFO queue for a slot that is already taken.
--
-- A patient who loses a booking race (or simply arrives late) joins the queue. When the
-- slot is released, the patient at the head is *offered* it: an exclusive, time-limited
-- claim window during which nobody else may book that slot.
--
-- Two engine-level guarantees, built the same way as uq_appointments_occupied_slot
-- above — project the predicate into a generated column, then index it UNIQUE. A UNIQUE
-- index skips rows where any indexed column is NULL, which is what lets inactive rows
-- accumulate freely while active ones stay constrained.
--
--   uq_waitlist_active_pair          one active place in a given queue per patient
--   uq_waitlist_one_offer_per_slot   AT MOST ONE outstanding offer per slot, ever
--
-- The second matters most: "two patients were both told the slot is theirs" becomes
-- impossible in the storage engine rather than merely unlikely in the application.
--
-- VIRTUAL again, not STORED: slot_id carries an ON DELETE CASCADE foreign key, and MySQL
-- forbids that on the base column of a STORED generated column (ERROR 1215).
-- -------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS slot_waitlist (
  id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  slot_id    BIGINT UNSIGNED NOT NULL,
  patient_id BIGINT UNSIGNED NOT NULL,
  status     ENUM('WAITING','OFFERED','CONVERTED','WITHDRAWN','EXPIRED')
             NOT NULL DEFAULT 'WAITING',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
             COMMENT 'Queue position is FIFO on (created_at, id)',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  offered_at       DATETIME NULL,
  offer_expires_at DATETIME NULL COMMENT 'End of the exclusive claim window',

  active_slot_id BIGINT UNSIGNED
    GENERATED ALWAYS AS (IF(status IN ('WAITING','OFFERED'), slot_id, NULL)) VIRTUAL,
  active_patient_id BIGINT UNSIGNED
    GENERATED ALWAYS AS (IF(status IN ('WAITING','OFFERED'), patient_id, NULL)) VIRTUAL,
  offered_slot_id BIGINT UNSIGNED
    GENERATED ALWAYS AS (IF(status = 'OFFERED', slot_id, NULL)) VIRTUAL,

  PRIMARY KEY (id),
  UNIQUE KEY uq_waitlist_active_pair (active_slot_id, active_patient_id),
  UNIQUE KEY uq_waitlist_one_offer_per_slot (offered_slot_id),
  KEY ix_waitlist_queue (slot_id, status, created_at, id),
  KEY ix_waitlist_patient (patient_id, status),
  CONSTRAINT fk_waitlist_slot FOREIGN KEY (slot_id)
    REFERENCES slots (id) ON DELETE CASCADE,
  CONSTRAINT fk_waitlist_patient FOREIGN KEY (patient_id)
    REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------------------------------
-- notifications — in-app inbox.
--
-- Written in the same transaction as the event they describe, so a notification can
-- never announce something that was rolled back.
--
-- The deep-link foreign keys are ON DELETE SET NULL, not CASCADE: a notification is a
-- historical record and should outlive the slot or appointment it points at.
-- -------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notifications (
  id      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL COMMENT 'Recipient',
  type    ENUM('APPOINTMENT_BOOKED','APPOINTMENT_CANCELLED','APPOINTMENT_COMPLETED',
               'SLOT_AVAILABLE','WAITLIST_JOINED','WAITLIST_MISSED','SLOT_WITHDRAWN')
          NOT NULL,
  title   VARCHAR(160) NOT NULL,
  body    VARCHAR(600) NULL,
  slot_id        BIGINT UNSIGNED NULL,
  appointment_id BIGINT UNSIGNED NULL,
  read_at    DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_notifications_user_unread (user_id, read_at, created_at),
  CONSTRAINT fk_notification_user FOREIGN KEY (user_id)
    REFERENCES users (id) ON DELETE CASCADE,
  CONSTRAINT fk_notification_slot FOREIGN KEY (slot_id)
    REFERENCES slots (id) ON DELETE SET NULL,
  CONSTRAINT fk_notification_appt FOREIGN KEY (appointment_id)
    REFERENCES appointments (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
