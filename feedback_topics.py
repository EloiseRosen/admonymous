import io


MAX_FEEDBACK_TOPICS = 25
MAX_FEEDBACK_TOPIC_LENGTH = 200

# Valid input is at most 5,024 characters plus incidental blank-line whitespace.
MAX_FEEDBACK_TOPICS_INPUT_LENGTH = 10_000

# Bleach can expand one input character ("&") to five serialized characters.
MAX_STORED_FEEDBACK_TOPIC_LENGTH = MAX_FEEDBACK_TOPIC_LENGTH * 5
MAX_STORED_FEEDBACK_TOPICS_LENGTH = (
    MAX_FEEDBACK_TOPICS * MAX_STORED_FEEDBACK_TOPIC_LENGTH
    + MAX_FEEDBACK_TOPICS
    - 1
)


class FeedbackTopicsValidationError(ValueError):
    pass


def _iter_nonblank_topics(value):
    for line in io.StringIO(value or "", newline=None):
        topic = line.rstrip("\n").strip()
        if topic:
            yield topic


def validate_feedback_topics(value):
    value = value or ""
    if len(value) > MAX_FEEDBACK_TOPICS_INPUT_LENGTH:
        raise FeedbackTopicsValidationError(
            "Feedback topics are too long. Enter no more than 25 topics, "
            "with up to 200 characters each."
        )

    topics = []
    for topic in _iter_nonblank_topics(value):
        if len(topics) >= MAX_FEEDBACK_TOPICS:
            raise FeedbackTopicsValidationError(
                "Enter no more than 25 feedback topics."
            )
        if len(topic) > MAX_FEEDBACK_TOPIC_LENGTH:
            raise FeedbackTopicsValidationError(
                "Each feedback topic must be 200 characters or fewer."
            )
        topics.append(topic)

    return topics


def canonicalize_feedback_topics(value, sanitizer):
    """Validate topics and return their safe, newline-delimited storage form."""
    cleaned_topics = []
    for topic in validate_feedback_topics(value):
        cleaned_topic = sanitizer(topic)
        cleaned_topic = (
            cleaned_topic.replace("\r\n", " ")
            .replace("\r", " ")
            .replace("\n", " ")
            .strip()
        )
        if not cleaned_topic:
            continue
        if len(cleaned_topic) > MAX_STORED_FEEDBACK_TOPIC_LENGTH:
            raise FeedbackTopicsValidationError(
                "Each feedback topic must be 200 characters or fewer."
            )
        cleaned_topics.append(cleaned_topic)

    return "\n".join(cleaned_topics)

