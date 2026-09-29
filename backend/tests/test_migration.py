from __future__ import annotations

import unittest

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.db.migration import _assign_orphan_conversations
from app.models.books import Book
from app.models.conversations import Conversation


class MigrationTests(unittest.TestCase):
    def test_orphan_conversations_assigned_to_first_book(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            book_a = Book(title="A", user_id="alice")
            book_b = Book(title="B", user_id="alice")
            session.add_all([book_a, book_b])
            session.commit()
            session.refresh(book_a)
            session.refresh(book_b)

            conv_alice = Conversation(user_id="alice", book_id=None, title="old chat")
            conv_bob = Conversation(user_id="bob", book_id=None, title="bob chat")
            session.add_all([conv_alice, conv_bob])
            session.commit()

            assigned = _assign_orphan_conversations(session)
            self.assertEqual(assigned, 1)
            session.refresh(conv_alice)
            session.refresh(conv_bob)
            self.assertEqual(conv_alice.book_id, book_a.id)
            self.assertIsNone(conv_bob.book_id)


if __name__ == "__main__":
    unittest.main()
