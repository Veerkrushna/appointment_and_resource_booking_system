import { useEffect, useRef, useState } from "react";

type ProviderOption = {
  id: string;
  name: string;
  averageRating: number | null;
  ratingCount: number;
};

type ProviderType = "person" | "resource";

type Props = {
  providers: ProviderOption[];
  providerTypes: Record<string, ProviderType>;
  selectedProviderId: string;
  disabled: boolean;
  onChange: (providerId: string) => void;
};

function formatRating(rating: number) {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 2,
  }).format(rating);
}

function hasRating(provider: ProviderOption) {
  return provider.averageRating != null && provider.ratingCount > 0;
}

function ProviderRatingSelect({
  providers,
  providerTypes,
  selectedProviderId,
  disabled,
  onChange,
}: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const choices: (ProviderOption | null)[] = [null, ...providers];
  const selectedIndex = Math.max(
    0,
    choices.findIndex((provider) => provider?.id === selectedProviderId),
  );
  const selectedProvider = choices[selectedIndex];

  useEffect(() => {
    if (!isOpen) return;
    const options =
      containerRef.current?.querySelectorAll<HTMLButtonElement>(
        '[role="option"]',
      );
    options?.[activeIndex]?.focus();
  }, [activeIndex, isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    function closeOnOutsideClick(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", closeOnOutsideClick);
    return () => document.removeEventListener("mousedown", closeOnOutsideClick);
  }, [isOpen]);

  function openAt(index: number) {
    setActiveIndex(index);
    setIsOpen(true);
  }

  function focusChoice(index: number) {
    const nextIndex = Math.max(0, Math.min(index, choices.length - 1));
    setActiveIndex(nextIndex);
    const options =
      containerRef.current?.querySelectorAll<HTMLButtonElement>(
        '[role="option"]',
      );
    options?.[nextIndex]?.focus();
  }

  function handleTriggerKeyDown(event: React.KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      openAt(selectedIndex);
    }
  }

  function handleOptionKeyDown(
    event: React.KeyboardEvent<HTMLButtonElement>,
    index: number,
  ) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      focusChoice(index + 1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      focusChoice(index - 1);
    } else if (event.key === "Home") {
      event.preventDefault();
      focusChoice(0);
    } else if (event.key === "End") {
      event.preventDefault();
      focusChoice(choices.length - 1);
    } else if (event.key === "Escape") {
      event.preventDefault();
      setIsOpen(false);
      triggerRef.current?.focus();
    }
  }

  function selectProvider(provider: ProviderOption | null) {
    onChange(provider?.id ?? "");
    setIsOpen(false);
    triggerRef.current?.focus();
  }

  function renderProviderDetail(provider: ProviderOption | null) {
    if (!provider) return null;
    if (providerTypes[provider.id] === "resource") {
      return <span className="provider-rating-select__detail">Resource</span>;
    }
    if (!hasRating(provider)) {
      return (
        <span className="provider-rating-select__detail">No ratings yet</span>
      );
    }
    return (
      <span className="provider-rating-select__detail">
        <span className="provider-rating-select__star" aria-hidden="true">
          ★
        </span>{" "}
        {formatRating(provider.averageRating!)} · {provider.ratingCount}{" "}
        {provider.ratingCount === 1 ? "review" : "reviews"}
      </span>
    );
  }

  return (
    <div
      className="booking-provider-filter"
      ref={containerRef}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          setIsOpen(false);
        }
      }}
    >
      <span className="booking-provider-filter__label">Provider</span>
      <button
        ref={triggerRef}
        className="booking-provider-filter__trigger"
        type="button"
        aria-label={`Provider: ${
          selectedProvider
            ? `${selectedProvider.name}, ${selectedLabelFor(
                selectedProvider,
                providerTypes,
              )}`
            : "All providers"
        }`}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls="booking-provider-options"
        disabled={disabled}
        onClick={() => openAt(selectedIndex)}
        onKeyDown={handleTriggerKeyDown}
      >
        <span className="booking-provider-filter__selection">
          {selectedProvider ? (
            <>
              <strong>{selectedProvider.name}</strong>
              {renderProviderDetail(selectedProvider)}
            </>
          ) : (
            <strong>All providers</strong>
          )}
        </span>
        <span className="booking-provider-filter__chevron" aria-hidden="true">
          {isOpen ? "▴" : "▾"}
        </span>
      </button>

      {isOpen && (
        <div
          className="booking-provider-filter__options"
          id="booking-provider-options"
          role="listbox"
          aria-label="Providers"
          aria-activedescendant={`booking-provider-option-${activeIndex}`}
        >
          {choices.map((provider, index) => (
            <button
              key={provider?.id ?? "all-providers"}
              id={`booking-provider-option-${index}`}
              className="booking-provider-filter__option"
              type="button"
              role="option"
              aria-selected={index === selectedIndex}
              aria-label={
                provider
                  ? `${provider.name}, ${selectedLabelFor(provider, providerTypes)}`
                  : "All providers"
              }
              tabIndex={index === activeIndex ? 0 : -1}
              onClick={() => selectProvider(provider)}
              onKeyDown={(event) => handleOptionKeyDown(event, index)}
            >
              {provider ? (
                <>
                  <strong>{provider.name}</strong>
                  {renderProviderDetail(provider)}
                </>
              ) : (
                <strong>All providers</strong>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function selectedLabelFor(
  provider: ProviderOption,
  providerTypes: Record<string, ProviderType>,
) {
  if (providerTypes[provider.id] === "resource") return "resource";
  if (!hasRating(provider)) return "no ratings yet";
  return `rated ${formatRating(provider.averageRating!)} out of 5, ${provider.ratingCount} reviews`;
}

export default ProviderRatingSelect;
