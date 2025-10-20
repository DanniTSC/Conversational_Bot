from enum import Enum, auto

class BotState(Enum):
    LISTENING = auto()
    THINKING  = auto()
    SPEAKING  = auto()
