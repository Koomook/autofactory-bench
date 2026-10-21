"""Request-scoped abstract inspection device, not a controller phase timer.

Latency is synthetic. Fixture permission must hold throughout the request;
DONE/result are valid only until the requester drops REQUEST.
"""
class RequestModule:
    def __init__(self, duration_ms, result=False):
        if duration_ms <= 0:
            raise ValueError('request duration must be positive')
        self.duration_ms = duration_ms
        self.result_value = bool(result)
        self.elapsed = 0.
        self.busy = self.done = self.previous_request = False
        self.accepted = self.completed_count = 0
        self.failed = False

    def tick(self, request, permitted, dt_ms):
        request = bool(request)
        faults = []
        if not request:
            if self.busy:
                faults.append('request_aborted')
            self.busy = self.done = self.failed = False
            self.elapsed = 0.
        else:
            if not self.previous_request:
                self.elapsed = 0.
                self.done = False
                self.failed = not permitted
                if permitted:
                    self.busy = True
                    self.accepted += 1
                else:
                    faults.append('request_without_fixture')
            if self.busy and not permitted:
                faults.append('fixture_lost_during_request')
                self.busy = False
                self.failed = True
            if self.busy:
                self.elapsed += dt_ms
                if self.elapsed >= self.duration_ms:
                    self.busy = False
                    self.done = True
                    self.completed_count += 1
        self.previous_request = request
        return faults

    @property
    def result(self):
        return self.done and self.result_value
