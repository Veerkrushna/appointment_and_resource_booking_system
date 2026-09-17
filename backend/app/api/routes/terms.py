from fastapi import APIRouter

router = APIRouter(prefix="/api/terms", tags=["Terms"])


@router.get("")
def service_booking_terms():
    return {
        "title": "Service Booking Terms",
        "version": "2026-09-17",
        "sections": [
            {
                "heading": "Booking an appointment",
                "content": "Customers are responsible for providing accurate contact details and selecting the correct service, provider, date, and time. An appointment is subject to provider availability and is confirmed only when the booking request is accepted by the service.",
            },
            {
                "heading": "Appointment changes and cancellations",
                "content": "Customers may cancel or reschedule appointments through their account, subject to the service provider's cancellation window and availability. A cancellation or reschedule request does not guarantee a refund or a replacement time unless the applicable service policy allows it.",
            },
            {
                "heading": "Customer responsibility",
                "content": "Customers should arrive on time and follow any preparation instructions supplied by the provider. Late arrival may reduce the available service time or be treated as a missed appointment.",
            },
            {
                "heading": "Notifications and communication",
                "content": "By creating an account, customers agree to receive essential booking confirmations, reminders, cancellation notices, and rescheduling updates through the contact details associated with their account.",
            },
            {
                "heading": "Service information",
                "content": "Service descriptions, prices, durations, provider availability, and applicable policies may change. The details shown at the time of booking apply to that appointment unless the provider communicates an approved change.",
            },
        ],
        "contact": "Contact the service provider if you need help with a booking or have questions about a service-specific policy.",
    }
