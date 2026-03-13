/**
 * export_comps.jsx
 * AdScreen Converter — After Effects Composition Exporter
 *
 * HOW TO USE:
 *   1. Open your After Effects project
 *   2. Go to File > Scripts > Run Script File...
 *   3. Select this file (export_comps.jsx)
 *   4. A JSON file is saved in the same folder as your .aep project
 *   5. Upload that JSON file in the AdScreen Converter app
 */

(function () {
    var project = app.project;

    if (!project || !project.file) {
        alert("Please save your After Effects project first, then run this script.");
        return;
    }

    // ── Collect all compositions ──────────────────────────────────────
    var comps = [];
    for (var i = 1; i <= project.numItems; i++) {
        var item = project.item(i);
        if (item instanceof CompItem) {
            comps.push({
                name:       item.name,
                width:      item.width,
                height:     item.height,
                frameRate:  Math.round(item.frameRate * 100) / 100,
                duration:   Math.round(item.duration * 100) / 100,
                pixelAspect: item.pixelAspect
            });
        }
    }

    if (comps.length === 0) {
        alert("No compositions found in this project.");
        return;
    }

    // ── Build JSON ────────────────────────────────────────────────────
    var projectName = project.file.name.replace(/\.[^\.]+$/, ""); // strip extension

    var output = {
        source:       "AfterEffects",
        project:      projectName,
        exported:     new Date().toISOString(),
        compositions: comps
    };

    // ── Serialise (no JSON.stringify in older ExtendScript) ───────────
    function escStr(s) {
        return s.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
    }

    function objToJson(obj, indent) {
        indent = indent || "";
        var inner = indent + "  ";
        var lines = [];
        for (var key in obj) {
            if (!obj.hasOwnProperty(key)) continue;
            var val = obj[key];
            var valStr;
            if (val === null) {
                valStr = "null";
            } else if (typeof val === "boolean") {
                valStr = val ? "true" : "false";
            } else if (typeof val === "number") {
                valStr = String(val);
            } else if (typeof val === "string") {
                valStr = '"' + escStr(val) + '"';
            } else if (val instanceof Array) {
                var items = [];
                for (var a = 0; a < val.length; a++) {
                    if (typeof val[a] === "object") {
                        items.push(objToJson(val[a], inner));
                    } else {
                        items.push('"' + escStr(String(val[a])) + '"');
                    }
                }
                valStr = "[\n" + inner + "  " + items.join(",\n" + inner + "  ") + "\n" + inner + "]";
            } else if (typeof val === "object") {
                valStr = objToJson(val, inner);
            }
            lines.push(inner + '"' + key + '": ' + valStr);
        }
        return "{\n" + lines.join(",\n") + "\n" + indent + "}";
    }

    var jsonStr = objToJson(output);

    // ── Save next to the .aep file ────────────────────────────────────
    var savePath = new File(project.file.parent.fsName + "/" + projectName + "_comps.json");
    savePath.open("w");
    savePath.write(jsonStr);
    savePath.close();

    alert(
        "Exported " + comps.length + " composition(s) to:\n" +
        savePath.fsName + "\n\n" +
        "Upload this JSON file in the AdScreen Converter app."
    );
})();
