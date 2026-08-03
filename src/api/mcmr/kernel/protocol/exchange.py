import json
import subprocess
import tempfile
from pathlib import Path
from time import perf_counter_ns
from typing import TYPE_CHECKING, cast

from .messages import KernelArgument, KernelStats, KernelStreamBatch

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping
    from typing import TextIO


class KernelExchange:
    """Own one incremental kernel process and its validated line protocol."""

    def __init__(self, binary: Path, stated: Mapping[str, KernelArgument], protocol: int) -> None:
        self.binary = binary
        self.stated = dict(stated)
        self.protocol = protocol

    def read(self) -> Generator[KernelStreamBatch | KernelStats]:
        """Yield families from one process and finish with its checked statistics."""
        with tempfile.TemporaryFile(mode="w+") as diagnostics:
            process = self._start(diagnostics)
            input_stream, output_stream = self._streams(process)
            try:
                yield from self._completed_response(
                    process,
                    input_stream=input_stream,
                    output_stream=output_stream,
                    diagnostics=diagnostics,
                )
            finally:
                self._close(process, output_stream)

    @staticmethod
    def _finish(process: subprocess.Popen[str], diagnostics: TextIO) -> None:
        """Require a successful exit and surface the kernel's diagnostic when it fails."""
        returncode = process.wait()
        diagnostics.seek(0)
        message = diagnostics.read().strip()
        if returncode:
            raise RuntimeError(f"the analysis kernel failed: {message}")

    @staticmethod
    def _record(line: str) -> KernelStreamBatch | KernelStats:
        """Validate and decode one record from the kernel stream."""
        kind, separator, payload = line.partition("\t")
        if not separator:
            raise RuntimeError("the analysis kernel wrote an invalid stream record")
        if kind == "F":
            return KernelStats.model_validate_json(payload)
        if kind != "B":
            raise RuntimeError("the analysis kernel wrote an invalid stream record")
        family, separator, facts = payload.partition("\t")
        if not family or not separator:
            raise RuntimeError("the analysis kernel wrote an invalid fact batch")
        return KernelStreamBatch(family=family, payload=facts)

    @staticmethod
    def _statistics(
        record: KernelStreamBatch | KernelStats,
        current: KernelStats | None,
    ) -> KernelStats | None:
        """Accept one batch or the one footer permitted by the stream contract."""
        if isinstance(record, KernelStreamBatch):
            if current is not None:
                raise RuntimeError("the analysis kernel wrote facts after its footer")
            return current
        if current is not None:
            raise RuntimeError("the analysis kernel wrote more than one footer")
        return record

    @staticmethod
    def _stop(process: subprocess.Popen[str]) -> None:
        """Stop a producer whose consumer left before reading the complete response."""
        if process.poll() is None:
            process.terminate()
            process.wait()

    @staticmethod
    def _streams(process: subprocess.Popen[str]) -> tuple[TextIO, TextIO]:
        """Return the two configured protocol pipes or fail if the process did not open them."""
        input_stream = process.stdin
        output_stream = process.stdout
        if input_stream is None or output_stream is None:
            process.terminate()
            process.wait()
            raise RuntimeError("the analysis kernel did not open its protocol streams")
        return cast("TextIO", input_stream), cast("TextIO", output_stream)

    @staticmethod
    def _validated_record(line: str) -> tuple[KernelStreamBatch | KernelStats, int]:
        """Return one decoded record and the time spent validating it."""
        started = perf_counter_ns()
        record = KernelExchange._record(line)
        return record, perf_counter_ns() - started

    @classmethod
    def _close(cls, process: subprocess.Popen[str], output_stream: TextIO) -> None:
        """Close the response pipe and stop a producer left alive by its consumer."""
        output_stream.close()
        cls._stop(process)

    @classmethod
    def _failed_response(
        cls,
        process: subprocess.Popen[str],
        diagnostics: TextIO,
        failure: RuntimeError,
    ) -> RuntimeError:
        """Finish a failed producer and preserve its protocol failure."""
        cls._finish(process, diagnostics)
        return failure

    def _completed_response(
        self,
        process: subprocess.Popen[str],
        *,
        input_stream: TextIO,
        output_stream: TextIO,
        diagnostics: TextIO,
    ) -> Generator[KernelStreamBatch | KernelStats]:
        """Complete one process exchange while the caller owns resource cleanup."""
        self._write(input_stream)
        header_line = output_stream.readline()
        if not header_line:
            self._finish(process, diagnostics)
            raise RuntimeError("the analysis kernel failed: no response was written")
        self._validate_header(header_line)
        try:
            statistics = yield from self._responses(output_stream)
        except RuntimeError as failure:
            raise self._failed_response(process, diagnostics, failure) from None
        self._finish(process, diagnostics)
        yield statistics

    def _responses(self, output: TextIO) -> Generator[KernelStreamBatch, None, KernelStats]:
        """Validate family and fact records, then return the one footer that ends them."""
        statistics: KernelStats | None = None
        validation_nanoseconds = 0
        for line in output:
            record, elapsed = self._validated_record(line)
            validation_nanoseconds += elapsed
            statistics = self._statistics(record, statistics)
            if isinstance(record, KernelStreamBatch):
                yield record
        if statistics is None:
            raise RuntimeError("the analysis kernel response ended without statistics")
        return statistics.model_copy(
            update={"protocol_validation_nanoseconds": validation_nanoseconds}
        )

    def _start(self, diagnostics: TextIO) -> subprocess.Popen[str]:
        """Start the kernel with independent protocol and diagnostic channels."""
        return subprocess.Popen(
            [str(self.binary)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=diagnostics,
            text=True,
        )

    def _validate_header(self, line: str) -> None:
        """Refuse a response shape or protocol version this release cannot interpret."""
        kind, separator, stated = line.rstrip("\n").partition("\t")
        try:
            version = int(stated) if kind == "H" and separator else None
        except ValueError:
            version = None
        if version is not None and version != self.protocol:
            raise RuntimeError(
                f"the analysis kernel speaks protocol {version} "
                f"and this release speaks {self.protocol}"
            )
        if version is None or stated != str(version):
            raise RuntimeError("the analysis kernel wrote an invalid stream header")

    def _write(self, input_stream: TextIO) -> None:
        """Send the complete request and close input so the kernel can begin."""
        input_stream.write(json.dumps(self.stated))
        input_stream.close()
