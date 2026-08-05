export default function Tabs({ value, options, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="tab"
          aria-selected={value === option.value}
          className={
            value === option.value ? 'tabs__tab tabs__tab--active' : 'tabs__tab'
          }
          onClick={() => onChange(option.value)}
        >
          {option.label}
          {option.count !== undefined && (
            <span className="tabs__count">{option.count}</span>
          )}
        </button>
      ))}
    </div>
  )
}
