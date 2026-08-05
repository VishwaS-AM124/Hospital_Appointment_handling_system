/** One function per REST endpoint, so pages never build URLs by hand. */

import { api, apiFetch } from './client'

// ------------------------------------------------------------------------------ auth

export const login = (email, password) =>
  apiFetch('/auth/login', { method: 'POST', body: { email, password }, auth: false })

export const register = (payload) =>
  apiFetch('/auth/register', { method: 'POST', body: payload, auth: false })

export const fetchMe = () => api.get('/auth/me')

// --------------------------------------------------------------------------- doctors

export const listDoctors = (q) => api.get('/doctors', { q })

export const listDoctorServices = (doctorId) =>
  api.get(`/doctors/${doctorId}/services`)

// -------------------------------------------------------------------------- services

export const listMyServices = () => api.get('/services/mine')
export const createService = (payload) => api.post('/services', payload)
export const updateService = (id, payload) => api.patch(`/services/${id}`, payload)
export const deleteService = (id) => api.delete(`/services/${id}`)

// ----------------------------------------------------------------------------- slots

export const listMySlots = (params) => api.get('/slots/mine', params)
export const listOpenSlots = (params) => api.get('/slots/open', params)
export const getSlot = (id) => api.get(`/slots/${id}`)
export const createSlot = (payload) => api.post('/slots', payload)
export const bulkCreateSlots = (payload) => api.post('/slots/bulk', payload)
export const updateSlot = (id, payload) => api.patch(`/slots/${id}`, payload)
export const deleteSlot = (id) => api.delete(`/slots/${id}`)

// ---------------------------------------------------------------------- appointments

export const bookAppointment = (slotId, reason) =>
  api.post('/appointments', { slot_id: slotId, reason: reason || null })

export const listMyAppointments = (params) => api.get('/appointments/mine', params)
export const listDoctorAppointments = (params) => api.get('/appointments/doctor', params)

export const cancelAppointment = (id, cancelReason) =>
  api.post(`/appointments/${id}/cancel`, { cancel_reason: cancelReason || null })

export const completeAppointment = (id, doctorNotes) =>
  api.post(`/appointments/${id}/complete`, { doctor_notes: doctorNotes || null })

// ------------------------------------------------------------------- waiting queue

export const listMyWaitlist = (activeOnly = true) =>
  api.get('/waitlist/mine', { active_only: activeOnly })

export const joinWaitlist = (slotId) => api.post(`/waitlist/slots/${slotId}`, {})

export const leaveWaitlist = (slotId) => api.delete(`/waitlist/slots/${slotId}`)

// -------------------------------------------------------------------- notifications

export const listNotifications = (params) => api.get('/notifications', params)

export const unreadCount = () => api.get('/notifications/unread-count')

export const markNotificationRead = (id) => api.post(`/notifications/${id}/read`, {})

export const markAllNotificationsRead = () => api.post('/notifications/read-all', {})
