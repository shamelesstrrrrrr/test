from typing import Any

from schemas import DInSARTaskInput


class ConversationState:
    def __init__(self) -> None:
        self.task_input = DInSARTaskInput()

    def update(self, **kwargs: Any) -> None:
        current_data = self.task_input.model_dump()
        current_data.update(kwargs)
        self.task_input = DInSARTaskInput(**current_data)

    def missing_fields(self) -> list[str]:
        return self.task_input.missing_fields()

    def is_complete(self) -> bool:
        return self.task_input.is_complete()

    def summary(self) -> dict:
        return self.task_input.model_dump(mode="json")