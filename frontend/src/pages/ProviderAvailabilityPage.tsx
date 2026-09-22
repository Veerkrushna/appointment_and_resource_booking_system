import { useState, useEffect } from "react";
import { useAuth } from "../auth/useAuth";

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

  const { customer, token } = useAuth();
  const [providerId, setProviderId] = useState<string | null>(null);
  const [blackoutDates, setBlackoutDates] = useState<any[]>([]);
  const [isAddingBlackout, setIsAddingBlackout] = useState(false);
  const [newBlackoutDate, setNewBlackoutDate] = useState("");
  const [newBlackoutReason, setNewBlackoutReason] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    async function fetchProviderData() {
      if (!customer?.email) return;
      try {
        const pRes = await fetch('/api/providers');
        if (!pRes.ok) return;
        const providers = await pRes.json();
        const provider = providers.find((p: any) => p.email === customer.email);
        if (provider) {
          setProviderId(provider.id);
          const bRes = await fetch(`/api/providers/${provider.id}/schedule`);
          if (bRes.ok) {
            const data = await bRes.json();
            setBlackoutDates(data.blackout_dates || []);
          }
        }
      } catch (err) {
        console.error("Failed to load provider data", err);
      }
    }
    void fetchProviderData();
  }, [customer?.email]);

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

  const handleConfirmBlackout = async () => {
    if (!providerId || !newBlackoutDate) return;
    try {
      const res = await fetch(`/api/providers/${providerId}/unavailability`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          start_date: newBlackoutDate,
          end_date: newBlackoutDate,
          reason: newBlackoutReason || "Unavailable"
        })
      });
      if (res.ok) {
        const newBlackout = await res.json();
        setBlackoutDates(prev => [...prev, newBlackout].sort((a, b) => new Date(a.blackout_start).getTime() - new Date(b.blackout_start).getTime()));
        setIsAddingBlackout(false);
        setNewBlackoutDate("");
        setNewBlackoutReason("");
      } else {
        alert("Failed to add blackout date");
      }
    } catch (err) {
      console.error(err);
      alert("Error adding blackout date");
    }
  };

  const handleDeleteBlackout = async (id: string) => {
    if (!providerId) return;
    try {
      const res = await fetch(`/api/providers/${providerId}/unavailability/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok || res.status === 204) {
        setBlackoutDates(prev => prev.filter(b => b.id !== id));
      }
    } catch (err) {
      console.error(err);
    }
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
            className="btn-accent btn-accent--inline" 
            onClick={handleSave} 
            disabled={isSaving}
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
              <div key={day} style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', padding: '1rem', gap: '1rem', backgroundColor: 'var(--bg-color)', borderRadius: 'var(--radius)', border: '1px solid var(--border-color)' }}>
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
                  <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '1rem' }}>
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
                    <strong>{new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(new Date(date.blackout_start || date.date))}</strong>
                    <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>{date.reason || "Unavailable"}</div>
                  </div>
                  <button onClick={() => handleDeleteBlackout(date.id)} aria-label="Remove blackout date" style={{ backgroundColor: 'white', border: '1px solid black', color: 'black', cursor: 'pointer', fontSize: '1.2rem', width: '2rem', height: '2rem', borderRadius: '4px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>&times;</button>
                </div>
              ))}
              {blackoutDates.length === 0 && (
                <div style={{ color: 'var(--text-muted)', fontSize: '0.9rem', fontStyle: 'italic' }}>No blackout dates configured.</div>
              )}
            </div>
            
            {isAddingBlackout ? (
              <div style={{ marginTop: '1rem', padding: '1rem', border: '1px solid var(--border-color)', borderRadius: '4px', backgroundColor: 'var(--panel-bg)' }}>
                <p style={{ margin: '0 0 0.5rem 0', fontWeight: 'bold' }}>Select Date</p>
                <input 
                  type="date" 
                  value={newBlackoutDate} 
                  onChange={(e) => setNewBlackoutDate(e.target.value)} 
                  style={{ width: '100%', padding: '0.5rem', marginBottom: '0.5rem', border: '1px solid var(--border-color)', borderRadius: '4px', color: 'var(--text-color)', backgroundColor: 'var(--bg-color)' }}
                />
                <input 
                  type="text" 
                  placeholder="Reason (optional)"
                  value={newBlackoutReason} 
                  onChange={(e) => setNewBlackoutReason(e.target.value)} 
                  style={{ width: '100%', padding: '0.5rem', marginBottom: '1rem', border: '1px solid var(--border-color)', borderRadius: '4px', color: 'var(--text-color)', backgroundColor: 'var(--bg-color)' }}
                />
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                  <button 
                    onClick={handleConfirmBlackout}
                    disabled={!newBlackoutDate}
                    style={{ flex: 1, padding: '0.5rem', backgroundColor: 'var(--accent-color)', color: 'var(--bg-color)', border: 'none', borderRadius: '4px', cursor: newBlackoutDate ? 'pointer' : 'not-allowed', fontWeight: 'bold', opacity: newBlackoutDate ? 1 : 0.6 }}
                  >
                    Confirm
                  </button>
                  <button 
                    onClick={() => setIsAddingBlackout(false)}
                    style={{ flex: 1, padding: '0.5rem', backgroundColor: 'transparent', color: 'var(--text-color)', border: '1px solid var(--border-color)', borderRadius: '4px', cursor: 'pointer' }}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <button 
                onClick={() => setIsAddingBlackout(true)}
                className="btn-accent btn-accent--full"
              >
                + Add Blackout Date
              </button>
            )}
          </section>

          <section className="dashboard-panel">
            <div className="dashboard-panel__heading">
              <div>
                <p className="panel-kicker">Daily Routine</p>
                <h2>Breaks</h2>
              </div>
            </div>
            <p className="dashboard-note" style={{ marginBottom: '1rem' }}>Standard breaks applied to every working day.</p>
            
            <div style={{ padding: '0.75rem', backgroundColor: 'var(--bg-color)', borderRadius: '4px', border: '1px solid var(--border-color)', display: 'flex', flexWrap: 'wrap', gap: '1rem', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <strong>Lunch Break</strong>
                <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>12:00 PM - 1:00 PM</div>
              </div>
              <button style={{ backgroundColor: 'white', border: '1px solid black', color: 'black', cursor: 'pointer', padding: '0.25rem 0.75rem', borderRadius: '4px', fontWeight: 'bold' }}>Edit</button>
            </div>
            
            <button className="btn-accent btn-accent--full">
              + Add Break
            </button>
          </section>
        </div>
      </div>
    </section>
  );
}
