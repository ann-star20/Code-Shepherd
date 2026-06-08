REQUEST_EVENTS = []


def log_request_event(user_id, path, payload):
    REQUEST_EVENTS.append({
        "user_id": user_id,
        "path": path,
        "payload": payload,
    })
    return len(REQUEST_EVENTS)


def get_event_count():
    return len(REQUEST_EVENTS)


def clear_events_for_test():
    REQUEST_EVENTS.clear()
