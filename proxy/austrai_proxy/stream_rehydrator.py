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
        # Add fuzzy variants for bracket-type codenames:
        # [EU_PII_1] → also match [EUPII1], [EU_PII1], [Eu_Pii_1], etc.
        expanded = dict(mappings)
        for codename, original in list(mappings.items()):
            if codename.startswith("[") and codename.endswith("]"):
                inner = codename[1:-1]
                # Variant without underscores: [EU_PII_1] → [EUPII1]
                no_under = inner.replace("_", "")
                variant = f"[{no_under}]"
                if variant not in expanded:
                    expanded[variant] = original
                # Variant with only trailing number underscore: [EUPII_1]
                parts = inner.rsplit("_", 1)
                if len(parts) == 2 and parts[1].isdigit():
                    compact = f"[{parts[0].replace('_', '')}_{parts[1]}]"
                    if compact not in expanded:
                        expanded[compact] = original

        self._mappings = expanded
        self._sorted = sorted(expanded.keys(), key=len, reverse=True)
        self._max_len = max(len(k) for k in expanded) if expanded else 0
        self._buffer = ""
        self._prefixes = self._build_prefixes()
        self.restored_count = 0  # count of codenames replaced during streaming

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
            count = result.count(codename)
            if count:
                result = result.replace(codename, self._mappings[codename])
                self.restored_count += count
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
                    self.restored_count += 1
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
