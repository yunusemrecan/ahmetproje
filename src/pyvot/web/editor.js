// Pyvot <-> Monaco köprüsü.
// Python tarafı window.pyvot.* fonksiyonlarını runJavaScript ile çağırır;
// editördeki olaylar QWebChannel üzerinden "bridge" nesnesine bildirilir.
"use strict";

let bridge = null;
let editor = null;
const models = new Map();      // uri -> monaco model
const savedVersion = new Map(); // uri -> kaydedildiği andaki alternativeVersionId
const lastDirty = new Map();    // uri -> son bildirilen kirli durumu
const viewStates = new Map();   // uri -> kaydırma/imleç durumu
let current = null;

function isDirty(uri) {
  const model = models.get(uri);
  return !!model && model.getAlternativeVersionId() !== savedVersion.get(uri);
}

function notifyDirty(uri) {
  const dirty = isDirty(uri);
  if (lastDirty.get(uri) !== dirty) {
    lastDirty.set(uri, dirty);
    if (bridge) bridge.dirtyChanged(uri, dirty);
  }
}

function showEmpty(text) {
  const empty = document.getElementById("empty");
  empty.textContent = text || "";
  empty.style.display = text ? "flex" : "none";
}

window.pyvot = {
  open(uri, text, language, eol) {
    let model = models.get(uri);
    if (!model) {
      model = monaco.editor.createModel(text, language, monaco.Uri.parse(uri));
      model.setEOL(eol === "\r\n" ? monaco.editor.EndOfLineSequence.CRLF : monaco.editor.EndOfLineSequence.LF);
      models.set(uri, model);
      savedVersion.set(uri, model.getAlternativeVersionId());
      lastDirty.set(uri, false);
      model.onDidChangeContent(() => notifyDirty(uri));
    }
    window.pyvot.activate(uri);
  },

  activate(uri) {
    const model = models.get(uri);
    if (!model) return;
    if (current && current !== uri && models.has(current)) {
      viewStates.set(current, editor.saveViewState());
    }
    editor.setModel(model);
    const state = viewStates.get(uri);
    if (state) editor.restoreViewState(state);
    current = uri;
    showEmpty("");
    editor.focus();
  },

  close(uri) {
    const model = models.get(uri);
    if (!model) return;
    if (current === uri) {
      editor.setModel(null);
      current = null;
    }
    model.dispose();
    models.delete(uri);
    savedVersion.delete(uri);
    lastDirty.delete(uri);
    viewStates.delete(uri);
  },

  // Kaydetmek için metni ve o anki sürümü döndürür; kayıttan sonra markSaved(uri, version).
  snapshot(uri) {
    const model = models.get(uri);
    if (!model) return null;
    return { text: model.getValue(), version: model.getAlternativeVersionId() };
  },

  markSaved(uri, version) {
    if (!models.has(uri)) return;
    savedVersion.set(uri, version);
    notifyDirty(uri);
  },

  isDirty(uri) {
    return isDirty(uri);
  },

  // Metni değiştirir (biçimlendirme, yeniden yükleme). Geri alma geçmişi korunur.
  setText(uri, text, markClean) {
    const model = models.get(uri);
    if (!model) return;
    // Satır sonu farkı (CRLF/LF) değişiklik sayılmasın.
    if (model.getValue(monaco.editor.EndOfLinePreference.LF) !== text.replace(/\r\n/g, "\n")) {
      model.pushEditOperations([], [{ range: model.getFullModelRange(), text }], () => null);
      model.pushStackElement();
    }
    if (markClean) savedVersion.set(uri, model.getAlternativeVersionId());
    notifyDirty(uri);
  },

  setMarkers(uri, markers) {
    const model = models.get(uri);
    if (!model) return;
    const severity = { error: monaco.MarkerSeverity.Error, warning: monaco.MarkerSeverity.Warning, info: monaco.MarkerSeverity.Info };
    monaco.editor.setModelMarkers(model, "ruff", markers.map((m) => ({
      severity: severity[m.severity] || monaco.MarkerSeverity.Warning,
      message: m.message,
      code: m.code || undefined,
      source: "ruff",
      startLineNumber: m.line,
      startColumn: m.column,
      endLineNumber: m.endLine || m.line,
      endColumn: m.endColumn || m.column + 1,
    })));
  },

  reveal(uri, line, column) {
    if (current !== uri) window.pyvot.activate(uri);
    const position = { lineNumber: line, column: column || 1 };
    editor.setPosition(position);
    editor.revealPositionInCenter(position);
    editor.focus();
  },

  setOptions(options) {
    editor.updateOptions(options);
    for (const model of models.values()) {
      const modelOptions = {};
      if (options.tabSize !== undefined) modelOptions.tabSize = options.tabSize;
      if (options.insertSpaces !== undefined) modelOptions.insertSpaces = options.insertSpaces;
      model.updateOptions(modelOptions);
    }
  },

  setTheme(dark) {
    monaco.editor.setTheme(dark ? "vs-dark" : "vs");
    document.body.style.setProperty("--bg", dark ? "#1e1e1e" : "#ffffff");
  },

  setEmptyText(text) {
    if (!current) showEmpty(text);
  },

  formatWithMonaco() {
    const action = editor.getAction("editor.action.formatDocument");
    if (action) action.run();
  },

  languages() {
    return monaco.languages.getLanguages().map((l) => l.id);
  },
};

function start() {
  new QWebChannel(qt.webChannelTransport, (channel) => {
    bridge = channel.objects.bridge;
    require.config({ paths: { vs: "monaco/vs" } });
    require(["vs/editor/editor.main"], () => {
      editor = monaco.editor.create(document.getElementById("editor"), {
        model: null,
        automaticLayout: true,
        fontSize: 14,
        minimap: { enabled: true },
        renderWhitespace: "selection",
        scrollBeyondLastLine: false,
        tabSize: 4,
        insertSpaces: true,
        rulers: [],
        unicodeHighlight: { ambiguousCharacters: false },
      });
      const K = monaco.KeyCode;
      const M = monaco.KeyMod;
      editor.addCommand(M.CtrlCmd | K.KeyS, () => bridge.command("save"));
      editor.addCommand(M.CtrlCmd | M.Shift | K.KeyS, () => bridge.command("save_all"));
      editor.addCommand(M.CtrlCmd | K.KeyW, () => bridge.command("close"));
      editor.addCommand(K.F5, () => bridge.command("run"));
      editor.addCommand(M.CtrlCmd | K.F5, () => bridge.command("run_file"));
      editor.addCommand(M.Shift | M.Alt | K.KeyF, () => bridge.command("format"));
      editor.onDidChangeCursorPosition((e) => bridge.cursor(e.position.lineNumber, e.position.column));
      bridge.ready();
    });
  });
}

start();
