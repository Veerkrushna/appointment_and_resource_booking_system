import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

type TermsSection = { heading: string; content: string };
type TermsDocument = { title: string; version: string; sections: TermsSection[]; contact: string };

function TermsPage() {
  const [terms, setTerms] = useState<TermsDocument | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/terms")
      .then((response) => response.ok ? response.json() : Promise.reject(new Error("Unable to load the terms.")))
      .then((data: TermsDocument) => setTerms(data))
      .catch((requestError) => setError(requestError instanceof Error ? requestError.message : "Unable to load the terms."));
  }, []);

  return <main className="terms-page">
    <Link className="terms-back-link" to="/register">&#8592; Back to registration</Link>
    {error && <p className="status-message status-message--error" role="alert">{error}</p>}
    {!terms && !error && <p className="status-message">Loading service booking terms...</p>}
    {terms && <article className="terms-document"><header><p className="eyebrow">Appointment Booking</p><h1>{terms.title}</h1><p className="terms-intro">Please review the terms that apply when booking and managing services through your customer account.</p><small>Version {terms.version}</small></header><div className="terms-sections">{terms.sections.map((section) => <section key={section.heading}><h2>{section.heading}</h2><p>{section.content}</p></section>)}</div><footer><p>{terms.contact}</p><Link className="primary-button" to="/register">Return to registration</Link></footer></article>}
  </main>;
}

export default TermsPage;
