import { Link } from "react-router-dom";

import { useAuth } from "../auth/useAuth";

function CustomerDashboardPage() {
  const { customer } = useAuth();
  return <section className="dashboard-page"><header className="dashboard-heading"><div><p className="eyebrow">Personal booking space</p><h1>Hello, {customer?.name.split(" ")[0]}</h1><p className="services-intro">Your appointments, details, and next visit in one calm place.</p></div></header><div className="dashboard-grid"><section className="dashboard-panel dashboard-panel--wide"><p className="panel-kicker">Your schedule</p><h2>Appointments</h2><p className="dashboard-note">View upcoming visits, review your history, or make a change when plans shift.</p><Link className="primary-button" to="/appointments">View my appointments</Link></section><section className="dashboard-panel"><p className="panel-kicker">Ready to book?</p><h2>Find a service</h2><p className="dashboard-note">Choose a provider and reserve a time that works for you.</p><Link className="secondary-button" to="/services">Browse services</Link></section></div></section>;
}

export default CustomerDashboardPage;
