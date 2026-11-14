from dataclasses import dataclass

from app.database.db import Database
from app.database.repositories import PaymentRepository, TrackRepository, UserRepository


@dataclass(frozen=True)
class Repositories:
    users: UserRepository
    tracks: TrackRepository
    payments: PaymentRepository


def build_repositories(db: Database) -> Repositories:
    return Repositories(
        users=UserRepository(db),
        tracks=TrackRepository(db),
        payments=PaymentRepository(db),
    )
