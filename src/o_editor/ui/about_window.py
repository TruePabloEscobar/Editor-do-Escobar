"""Product credits and a concise, truthful first-use guide."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout, QWidget

from o_editor.ui.theme import PALETTE

DEVELOPER_URL = "https://pabloescobardj.web.app/Wikipedia-Pablo-Escobar.html"


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sobre — Editor Do Escobar")
        self.resize(620, 520)
        layout = QVBoxLayout(self)
        self.content = QTextBrowser()
        self.content.setOpenExternalLinks(True)
        self.content.setHtml(f"""
            <h2>Editor Do Escobar — EDE</h2>
            <p>Desenvolvido por
            <a style="color: {PALETTE["sand"]}" href="{DEVELOPER_URL}">Pablo Escobar</a>.</p>
            <h3>Como usar</h3>
            <ol>
            <li>No DaVinci Resolve Studio 21, abra Área de Trabalho → Scripts → O EDITOR.
            Se trocar o clipe ou a timeline, clique em Atualizar timeline.</li>
            <li>Em Faixas de voz, marque os microfones que deseja transcrever.</li>
            <li>Na engrenagem, carregue ou baixe um modelo, escolha CPU/GPU e salve.</li>
            <li>Em Transcrição, transcreva as faixas selecionadas. Em Revisão, corrija o texto
            e marque as falas que deseja cortar. É possível exportar/importar TXT.</li>
            <li>Em Prévia e cortes, ajuste os silêncios e a limpeza de microfones.
            Gere a prévia, valide e confirme Aplicar Rough Cut. O resultado é criado numa
            nova timeline; a original é preservada.</li>
            </ol>
            <p>A limpeza de retorno é opcional. Confira o resultado por escuta:
            falas simultâneas e reações devem ser preservadas.</p>
            <p>Zoom e Legendas são ferramentas separadas de sugestões. Legendas oferece
            sugestões de texto, não legendagem integral. A aplicação de zoom/texto no
            Resolve permanece em preflight quando a capacidade não foi comprovada.</p>
            <p>A transcrição roda no computador. A internet só é necessária para instalar
            dependências e baixar modelos quando você solicitar.</p>
        """)
        layout.addWidget(self.content)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Fechar")
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
