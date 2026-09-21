import { useState } from "react";

type DaySchedule = {
  active: boolean;
  start: string;
  end: string;
};

type WeeklySchedule = Record<string, DaySchedule>;

export default function ProviderAvailabilityPage() {
  const [schedule, setSchedule] = useState<WeeklySchedule>({
    Monday: { active: true, start: "09:00", end: "17:00" },
    Tuesday: { active: true, start: "09:00", end: "17:00" },
    Wednesday: { active: true, start: "09:00", end: "17:00" },
    Thursday: { active: true, start: "09:00", end: "17:00" },
    Friday: { active: true, start: "09:00", end: "15:00" },
    Saturday: { active: false, start: "10:00", end: "14:00" },
    Sunday: { active: false, start: "10:00", end: "14:00" },
  });

  const [blackoutDates] = useState([
    { id: "1", date: "2026-10-15", reason: "Vacation" },
    { id: "2", date: "2026-11-20", reason: "Medical Leave" }
  ]);

  const [isSaving, setIsSaving] = useState(false);

  const toggleDay = (day: string) => {
    setSchedule(prev => ({
      ...prev,
      [day]: { ...prev[day], active: !prev[day].active }
    }));
  };

  const updateTime = (day: string, field: 'start' | 'end', value: string) => {
    setSchedule(prev => ({
      ...prev,
      [day]: { ...prev[day], [field]: value }
    }));
  };

  const handleSave = () => {
    setIsSaving(true);
    setTimeout(() => {
      setIsSaving(false);
      alert("Availability settings saved successfully!");
    }, 800);
  };

  return (
    <section className="dashboard-page">
      <header className="dashboard-heading">
        <div>
          <p className="eyebrow">Settings</p>
          <h1>Availability</h1>
          <p className="services-intro">Manage your weekly working hours, breaks, and blackout dates.</p>
        </div>
        <div>
          <button 
            className="action-button" 
            onClick={handleSave} 
            disabled={isSaving}
            style={{ padding: '0.75rem 1.5rem', backgroundColor: 'var(--accent-color)', color: 'var(--bg-color)', border: 'none', borderRadius: 'var(--radius)', cursor: 'pointer', fontWeight: 'bold' }}
          >
            {isSaving ? "Saving..." : "Save Changes"}
          </button>
        </div>
      </header>

      <div className="dashboard-grid">
        <section className="dashboard-panel dashboard-panel--wide">
          <div className="dashboard-panel__heading">
            <div>
              <p className="panel-kicker">Standard Hours</p>
              <h2>Weekly Schedule</h2>
            </div>
          </div>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1rem' }}>
            {Object.entries(schedule).map(([day, data]) => (
              <div key={day} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '1rem', backgroundColor: 'var(--bg-color)', borderRadius: 'var(--radius)', border: '1px solid var(--border-color)' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '1rem', width: '150px', cursor: 'pointer' }}>
                  <input 
                    type="checkbox" 
                    checked={data.active} 
                    onChange={() => toggleDay(day)} 
                    style={{ width: '1.2rem', height: '1.2rem', cursor: 'pointer' }}
                  />
                  <strong style={{ opacity: data.active ? 1 : 0.5 }}>{day}</strong>
                </label>
                
                {data.active ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                    <input 
                      type="time" 
                      value={data.start}
                      onChange={(e) => updateTime(day, 'start', e.target.value)}
                      style={{ padding: '0.5rem', borderRadius: '4px', border: '1px solid var(--border-color)', backgroundColor: 'var(--panel-bg)', color: 'var(--text-color)' }}
                    />
                    <span>to</span>
                    <input 
                      type="time" 
                      value={data.end}
                      onChange={(e) => updateTime(day, 'end', e.target.value)}
                      style={{ padding: '0.5rem', borderRadius: '4px', border: '1px solid var(--border-color)', backgroundColor: 'var(--panel-bg)', color: 'var(--text-color)' }}
                    />
                  </div>
                ) : (
                  <div style={{ color: 'var(--text-muted)', fontStyle: 'italic', width: '220px', textAlign: 'center' }}>
                    Unavailable
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          <section className="dashboard-panel">
            <div className="dashboard-panel__heading">
              <div>
                <p className="panel-kicker">Exceptions</p>
                <h2>Blackout Dates</h2>
              </div>
            </div>
            <p className="dashboard-note" style={{ marginBottom: '1rem' }}>Days you are completely unavailable (e.g., vacation).</p>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {blackoutDates.map(date => (
                <div key={date.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.75rem', backgroundColor: 'var(--bg-color)', borderRadius: '4px', border: '1px solid var(--border-color)' }}>
                  <div>
                    <strong>{new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(new Date(date.date))}</strong>
                    <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>{date.reason}</div>
                  </div>
                  <button style={{ background: 'none', border: 'none', color: 'var(--error-color)', cursor: 'pointer', fontSize: '1.2rem' }}>&times;</button>
                </div>
              ))}
            </div>
            <button style={{ marginTop: '1rem', width: '100%', padding: '0.75rem', backgroundColor: 'transparent', border: '1px dashed var(--border-color)', borderRadius: '4px', color: 'var(--text-color)', cursor: 'pointer' }}>
              + Add Blackout Date
            </button>
          </section>

          <section className="dashboard-panel">
            <div className="dashboard-panel__heading">
              <div>
                <p className="panel-kicker">Daily Routine</p>
                <h2>Breaks</h2>
              </div>
            </div>
            <p className="dashboard-note" style={{ marginBottom: '1rem' }}>Standard breaks applied to every working day.</p>
            
            <div style={{ padding: '0.75rem', backgroundColor: 'var(--bg-color)', borderRadius: '4px', border: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <strong>Lunch Break</strong>
                <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>12:00 PM - 1:00 PM</div>
              </div>
              <button style={{ background: 'none', border: 'none', color: 'var(--accent-color)', cursor: 'pointer' }}>Edit</button>
            </div>
            
            <button style={{ marginTop: '1rem', width: '100%', padding: '0.75rem', backgroundColor: 'transparent', border: '1px dashed var(--border-color)', borderRadius: '4px', color: 'var(--text-color)', cursor: 'pointer' }}>
              + Add Break
            </button>
          </section>
        </div>
      </div>
    </section>
  );
}
