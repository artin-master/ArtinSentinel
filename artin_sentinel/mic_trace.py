"""Operator-facing summary of experimental DVRIP microphone stages."""

from dataclasses import dataclass
import re


@dataclass
class MicTrace:
    connected: bool = False
    started: bool = False
    captured: bool = False
    frames: int = 0
    error: str = ""

    def observe(self, line: str) -> str:
        text = str(line or "")
        if "DVRIP 1/6" in text:
            self.connected = True
        if "DVRIP 4/6" in text:
            self.started = True
        if "DVRIP 5/6" in text:
            self.captured = True
        match = re.search(r"PTT envio\s*•\s*(\d+) frame", text)
        if match:
            self.frames = max(self.frames, int(match.group(1)))
        if ("falhou:" in text.lower() or "microfone não forneceu áudio" in text.lower()
                or "ret=504" in text.lower()):
            self.error = text.split("PTT • ")[-1][-180:]
        return self.summary()

    def summary(self) -> str:
        if self.error:
            return f"MIC • falha: {self.error}"
        if self.frames:
            return f"MIC • {self.frames} pacote(s) enviados pelo PC; confirme som na câmera"
        if self.captured:
            return "MIC • capturando áudio local; aguardando envio"
        if self.started:
            return "MIC • câmera aceitou início; aguardando microfone"
        if self.connected:
            return "MIC • conexão autenticada; preparando canal de áudio"
        return "MIC • iniciando conexão"
