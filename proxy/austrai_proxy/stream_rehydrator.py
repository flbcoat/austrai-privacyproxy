"""Sliding-window streaming rehydrator for SSE responses.

Replaces codenames and bracket references in a streaming text with original
values, handling the case where a codename might span multiple SSE chunks.

Uses a prefix-set approach: buffer characters until we can confirm they
don't start any codename, then flush safely. Maximum delay = length of
longest codename (typically 5-15 chars, imperceptible at 40 tokens/sec).
"""


class StreamRehydrator:
    """Rehydrates streaming LLM responses by replacing codenames with originals.

    Usage:
        r = StreamRehydrator({"Arion": "Thomas Gruber", "[AT_IBAN_1]": "AT48..."})
        for chunk in sse_stream:
            safe = r.feed(chunk)
            if safe:
                yield safe
        yield r.flush()  # emit any remaining buffered text
    """

    def __init__(self, mappings: dict[str, str]):
        self._mappings = mappings
        self._sorted = sorted(mappings.keys(), key=len, reverse=True)
        self._max_len = max(len(k) for k in mappings) if mappings else 0
        self._buffer = ""
        self._prefixes = self._build_prefixes()

    def _build_prefixes(self) -> set[str]:
        """Build set of all valid prefixes of all codenames."""
        prefixes: set[str] = set()
        for codename in self._mappings:
            for i in range(1, len(codename) + 1):
                prefixes.add(codename[:i])
        return prefixes

    def feed(self, chunk: str) -> str:
        """Feed a text chunk, return text safe to emit."""
        if not self._mappings:
            return chunk  # passthrough if no mappings
        self._buffer += chunk
        return self._flush()

    def flush(self) -> str:
        """Flush remaining buffer (call at end of stream)."""
        if not self._buffer:
            return ""
        result = self._buffer
        for codename in self._sorted:
            result = result.replace(codename, self._mappings[codename])
        self._buffer = ""
        return result

    def _flush(self) -> str:
        output: list[str] = []

        while self._buffer:
            # Check for complete codename match at start of buffer
            matched = False
            for codename in self._sorted:
                if self._buffer.startswith(codename):
                    output.append(self._mappings[codename])
                    self._buffer = self._buffer[len(codename):]
                    matched = True
                    break
            if matched:
                continue

            # Check if entire buffer is a prefix of some codename -> wait
            if self._buffer in self._prefixes:
                break

            # Find earliest position where a prefix match starts
            hold_from = len(self._buffer)
            for i in range(1, len(self._buffer)):
                suffix = self._buffer[i:]
                if suffix in self._prefixes:
                    hold_from = i
                    break

            if hold_from < len(self._buffer):
                output.append(self._buffer[:hold_from])
                self._buffer = self._buffer[hold_from:]
            else:
                # First char can't start any codename -> safe to emit
                output.append(self._buffer[0])
                self._buffer = self._buffer[1:]

        return "".join(output)
