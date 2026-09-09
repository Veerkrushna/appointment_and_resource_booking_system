import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

type Service = {
  id: string;
  name: string;
  description: string | null;
  duration_minutes: number;
  price: string | number | null;
  category: string;
  status: "active" | "inactive";
};

function formatPrice(price: Service["price"]) {
  if (price === null) {
    return "Price on request";
  }

  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(Number(price));
}

function ServicesPage() {
  const [services, setServices] = useState<Service[]>([]);
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isCurrent = true;

    async function loadServices() {
      try {
        const response = await fetch("/api/services");
        if (!response.ok) {
          throw new Error("Unable to load services.");
        }

        const data: Service[] = await response.json();
        if (isCurrent) {
          setServices(data.filter((service) => service.status === "active"));
        }
      } catch (requestError) {
        if (isCurrent) {
          setError(
            requestError instanceof Error
              ? requestError.message
              : "Unable to load services.",
          );
        }
      } finally {
        if (isCurrent) {
          setIsLoading(false);
        }
      }
    }

    void loadServices();

    return () => {
      isCurrent = false;
    };
  }, []);

  const categories = useMemo(
    () => [
      "All",
      ...Array.from(new Set(services.map((service) => service.category))).sort(),
    ],
    [services],
  );

  const visibleServices = useMemo(
    () =>
      selectedCategory === "All"
        ? services
        : services.filter((service) => service.category === selectedCategory),
    [selectedCategory, services],
  );

  return (
    <section className="services-page">
      <div className="services-heading">
        <div>
          <p className="eyebrow">Find your next appointment</p>
          <h1>Services</h1>
          <p className="services-intro">
            Browse our active services and choose the right fit for your schedule.
          </p>
        </div>
        {!isLoading && !error && (
          <p className="service-count">
            <strong>{services.length}</strong> active {services.length === 1 ? "service" : "services"}
          </p>
        )}
      </div>

      {isLoading && <p className="status-message">Loading services...</p>}

      {error && (
        <div className="status-message status-message--error" role="alert">
          <strong>We could not load the service list.</strong>
          <span>{error}</span>
        </div>
      )}

      {!isLoading && !error && services.length > 0 && (
        <>
          <div className="category-filter" aria-label="Filter services by category">
            {categories.map((category) => (
              <button
                className={selectedCategory === category ? "filter-button active" : "filter-button"}
                key={category}
                onClick={() => setSelectedCategory(category)}
                type="button"
              >
                {category}
              </button>
            ))}
          </div>

          {visibleServices.length > 0 ? (
            <div className="service-grid">
              {visibleServices.map((service) => (
                <article className="service-card" key={service.id}>
                  <div className="service-card__topline">
                    <span className="service-category">{service.category}</span>
                    <span className="service-arrow" aria-hidden="true">&#8599;</span>
                  </div>
                  <h2>{service.name}</h2>
                  <p className="service-description">
                    {service.description || "Details for this service are coming soon."}
                  </p>
                  <div className="service-meta">
                    <span>{service.duration_minutes} min</span>
                    <span>{formatPrice(service.price)}</span>
                  </div>
                  <Link className="service-book-link" to={`/book/${service.id}`}>
                    Book this service <span aria-hidden="true">&#8594;</span>
                  </Link>
                </article>
              ))}
            </div>
          ) : (
            <p className="status-message">No services in this category yet.</p>
          )}
        </>
      )}

      {!isLoading && !error && services.length === 0 && (
        <div className="empty-services">
          <span className="empty-services__mark" aria-hidden="true">+</span>
          <h2>No services available yet</h2>
          <p>Check back soon for new ways to book time with our team.</p>
        </div>
      )}
    </section>
  );
}

export default ServicesPage;
