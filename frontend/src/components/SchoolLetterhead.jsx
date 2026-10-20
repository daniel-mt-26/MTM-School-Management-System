export default function SchoolLetterhead({ school }) {
  return <header className="statement-letterhead" style={{ borderColor: school.brand_color }}>
    {school.logo_data ? <img src={`data:image/png;base64,${school.logo_data}`} alt={`${school.name} logo`} /> : school.logo && <img src={school.logo} alt={`${school.name} logo`} />}
    <h2>{school.name}</h2>{['motto', 'address', 'phone', 'additional_contacts', 'email', 'website'].map(key => school[key] && <p key={key}>{school[key]}</p>)}
  </header>
}
