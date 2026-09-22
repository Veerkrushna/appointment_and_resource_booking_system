import { useState } from "react";

type Service = {
  id: string;
  name: string;
  description: string;
  price: number;
  duration_minutes: number;
  active: boolean;
};

export default function ProviderServicesPage() {
  const [services, setServices] = useState<Service[]>([
    { id: "1", name: "Consultation", description: "Initial consultation for new patients.", price: 50, duration_minutes: 30, active: true },
    { id: "2", name: "Massage Therapy", description: "Full body massage therapy.", price: 100, duration_minutes: 60, active: true },
    { id: "3", name: "Follow-up", description: "Follow-up checkup.", price: 40, duration_minutes: 20, active: false }
  ]);

  const toggleService = (id: string) => {
    setServices(prev => prev.map(s => s.id === id ? { ...s, active: !s.active } : s));
  };

  return (
    <section className="dashboard-page">
      <header className="dashboard-heading">
        <div>
          <p className="eyebrow">Offerings</p>
          <h1>My Services</h1>
          <p className="services-intro">Manage the services you offer to customers.</p>
        </div>
        <div>
          <button className="btn-accent btn-accent--full">
            + Add New Service
          </button>
        </div>
      </header>

      <div className="dashboard-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 300px), 1fr))' }}>
        {services.map(service => (
          <section key={service.id} className="dashboard-panel" style={{ opacity: service.active ? 1 : 0.6, display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '1.25rem' }}>{service.name}</h3>
                <span className={`dashboard-status dashboard-status--${service.active ? 'completed' : 'cancelled'}`} style={{ marginTop: '0.5rem', display: 'inline-block' }}>
                  {service.active ? 'Active' : 'Inactive'}
                </span>
              </div>
              <strong style={{ fontSize: '1.25rem', color: 'var(--accent-color)' }}>
                ${service.price}
              </strong>
            </div>
            
            <p style={{ color: 'var(--text-muted)', margin: 0, flexGrow: 1 }}>
              {service.description}
            </p>
            
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', justifyContent: 'space-between', alignItems: 'center', paddingTop: '1rem', borderTop: '1px solid var(--border-color)' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-muted)' }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10"></circle>
                  <polyline points="12 6 12 12 16 14"></polyline>
                </svg>
                {service.duration_minutes} min
              </span>
              
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button 
                  onClick={() => toggleService(service.id)}
                  style={{ padding: '0.5rem 1rem', backgroundColor: 'transparent', border: '1px solid var(--border-color)', borderRadius: '4px', color: 'var(--text-color)', cursor: 'pointer' }}
                >
                  {service.active ? 'Deactivate' : 'Activate'}
                </button>
                <button 
                  style={{ padding: '0.5rem 1rem', backgroundColor: 'var(--bg-color)', border: '1px solid var(--accent-color)', borderRadius: '4px', color: 'var(--accent-color)', cursor: 'pointer' }}
                >
                  Edit
                </button>
              </div>
            </div>
          </section>
        ))}
      </div>
    </section>
  );
}
