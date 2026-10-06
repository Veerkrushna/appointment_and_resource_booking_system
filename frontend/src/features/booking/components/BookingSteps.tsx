
type Props = {
  steps: string[];
  currentStep: number;
};

export default function BookingSteps({ steps, currentStep }: Props) {
  return (
    <div className="booking-steps" aria-label="Booking progress">
      {steps.map((label, index) => {
        const stepNumber = index + 1;
        return (
          <div
            className={
              currentStep >= stepNumber ? "booking-step active" : "booking-step"
            }
            key={label}
          >
            <span>{stepNumber}</span>
            <small>{label}</small>
          </div>
        );
      })}
    </div>
  );
}
