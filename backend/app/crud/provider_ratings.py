from sqlalchemy import func, select

from app.models.providers import Provider, ProviderType
from app.models.review import Review


def provider_rating_subquery():
    return (
        select(
            Review.provider_id.label("provider_id"),
            func.round(func.avg(Review.rating), 2).label("average_rating"),
            func.count(Review.id).label("rating_count"),
        )
        .join(Provider, Provider.id == Review.provider_id)
        .where(Provider.type == ProviderType.PERSON)
        .group_by(Review.provider_id)
        .subquery("provider_rating_aggregates")
    )
