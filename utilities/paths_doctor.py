"""
Report where IQEA reads and writes artifacts, and what is actually there.

Run inside the container when the UI shows no action files / screenshots /
test cases / page files:

    cd /app && python -m utilities.paths_doctor

There are two very different causes and they need opposite fixes:

  * FOLDER MISSING or resolved somewhere unexpected -> a path problem. Every
    artifact path is built from `os.getcwd()`, so the process's working
    directory decides everything. supervisord sets `directory=/app`; if the app
    is ever started from elsewhere, the folders move with it.

  * FOLDER EXISTS BUT EMPTY -> not a path problem. Either nothing has been
    generated yet, or it was generated and lost. `output/` is excluded by
    .dockerignore (deliberately - it holds 140+ MB of local recordings), so a
    fresh container starts empty, and App Service container storage is
    EPHEMERAL: everything written is discarded on restart, redeploy or
    scale-in. Persisting artifacts needs an Azure Files mount at /app/output.
"""

import os


def _folders():
    """The artifact folders the UI reads, resolved the same way the app does."""
    cwd = os.getcwd()
    out = os.path.join(cwd, "output")
    return [
        ("cwd (decides everything)", cwd),
        ("Input", os.path.join(cwd, "Input")),
        ("output", out),
        ("action files", os.path.join(out, "Action_collection")),
        ("action screenshots", os.path.join(out, "Action_collection", "Sauce_demo")),
        ("desktop actions", os.path.join(out, "Action_collection",
                                         "Action_collection_desktop")),
        ("test files", os.path.join(out, "test_file_generator")),
        ("xpath details", os.path.join(out, "xpath_generator")),
        ("test cases", os.path.join(out, "Test_Cases_collection")),
        ("page files", os.path.join(out, "page_file_generator")),
        ("self-healing actions",
         os.path.join(cwd, "Self_healing_web_application", "output",
                      "Action_collection")),
        ("generated features", os.path.join(cwd, "generated_features")),
    ]


def report():
    print("IQEA artifact path report")
    print("=" * 74)
    problems = 0
    for label, path in _folders():
        if label.startswith("cwd"):
            print("  %-22s %s" % (label, path))
            continue
        if not os.path.isdir(path):
            print("  %-22s MISSING   %s" % (label, path))
            problems += 1
            continue
        try:
            names = [n for n in os.listdir(path)
                     if os.path.isfile(os.path.join(path, n))]
            subdirs = [n for n in os.listdir(path)
                       if os.path.isdir(os.path.join(path, n))]
        except OSError as exc:
            print("  %-22s UNREADABLE (%s)  %s" % (label, exc, path))
            problems += 1
            continue
        print("  %-22s %3d file(s), %d subdir(s)   %s"
              % (label, len(names), len(subdirs), path))
        for n in sorted(names)[:3]:
            print("  %-22s     - %s" % ("", n))
        if len(names) > 3:
            print("  %-22s     ... and %d more" % ("", len(names) - 3))

    print()
    writable = _check_writable(os.path.join(os.getcwd(), "output"))
    print("  output/ writable      : %s" % writable)
    print()
    if problems:
        print("  %d folder(s) missing or unreadable -> PATH problem." % problems)
        print("  Check the process working directory above is the repo root")
        print("  (/app in the container). supervisord sets directory=/app.")
    else:
        print("  All folders resolve. If they are EMPTY, this is not a path")
        print("  problem:")
        print("    - output/ is excluded by .dockerignore, so a fresh container")
        print("      starts with nothing in it")
        print("    - App Service container storage is EPHEMERAL - anything the")
        print("      app writes is lost on restart, redeploy or scale-in")
        print("  To keep artifacts, mount Azure Files at /app/output:")
        print("    az webapp config storage-account add --name <APP> \\")
        print("      --resource-group <RG> --custom-id iqea-output \\")
        print("      --storage-type AzureFiles --account-name <STORAGE> \\")
        print("      --share-name iqea-output --access-key <KEY> \\")
        print("      --mount-path /app/output")
    return 0 if not problems else 1


def _check_writable(path):
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".iqea_write_probe")
        with open(probe, "w") as fh:
            fh.write("ok")
        os.remove(probe)
        return "yes"
    except Exception as exc:
        return "NO (%s: %s)" % (type(exc).__name__, exc)


if __name__ == "__main__":
    raise SystemExit(report())
