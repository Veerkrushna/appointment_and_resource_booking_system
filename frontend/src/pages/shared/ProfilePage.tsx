import { useAuth } from "../auth/useAuth";

function ProfilePage() {
  const { customer } = useAuth();

  return (
    <section className="profile-page">
      <div className="services-heading">
        <div>
          <p className="eyebrow">Your account</p>
          <h1>Profile</h1>
          <p className="services-intro">
            Your customer details used for appointment bookings.
          </p>
        </div>
      </div>
      <dl className="profile-details">
        <div>
          <dt>Name</dt>
          <dd>{customer?.name}</dd>
        </div>
        <div>
          <dt>Email</dt>
          <dd>{customer?.email}</dd>
        </div>
        <div>
          <dt>Phone</dt>
          <dd>{customer?.phone || "Not provided"}</dd>
        </div>
      </dl>
    </section>
  );
}

export default ProfilePage;
