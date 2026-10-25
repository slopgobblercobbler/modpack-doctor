# Modpack Doctor 🩺

[![PyPI version](https://img.shields.io/badge/pypi-v1.0.0-blue.svg)](https://pypi.org/project/modpack-doctor/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-green.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-83%20passed-brightgreen.svg)](tests/)

**Modpack Doctor** is a production-grade diagnostic CLI tool and static analyzer for Minecraft modpacks. It scans your `.minecraft/mods` directory, parses embedded mod manifests (`fabric.mod.json`, `META-INF/mods.toml`, `META-INF/neoforge.mods.toml`, `quilt.mod.json`), constructs full dependency graphs, and flags crashes before you even launch the game.

---

## ⚡ Features

- **Multi-Loader Support**: Analyzes Fabric, NeoForge, Forge, and Quilt mod manifests in milliseconds without extracting entire JAR files.
- **Dependency Graph & Collision Resolver**:
  - Detects missing mandatory dependencies.
  - Identifies incompatible SemVer ranges and version conflicts.
  - Flags duplicate JARs and shadow-bundled libraries.
- **Mixin Collision Auditor**: Detects overlapping Mixin targets across different mods targeting the same vanilla methods (common cause of launch crashes).
- **Client/Server Environment Guard**: Warns if client-only mods (e.g. Sodium, Iris, MiniHUD) are present in server packs, or server-only mods are in client installations.
- **Multiple Output Formats**: Human-readable color terminal reports, JSON for CI/CD modpack builders, and Markdown tables.

---

## 🚀 Quick Start

### Installation

```bash
pip install modpack-doctor
```

Or run directly from source:

```bash
git clone https://github.com/slopgobblercobbler/modpack-doctor.git
cd modpack-doctor
pip install -e .
```

### Usage

Scan your local `.minecraft/mods` directory:

```bash
modpack-doctor scan C:/Users/YourName/AppData/Roaming/.minecraft/mods
```

Scan and output machine-readable JSON:

```bash
modpack-doctor scan ./mods --format json > report.json
```

Filter by specific loader or Minecraft version:

```bash
modpack-doctor scan ./mods --mc-version 1.21.1 --loader fabric
```

---

## 📊 Sample Diagnostic Output

```text
🩺 Modpack Doctor v1.0.0 - Audit Report
Target: C:\Users\User\AppData\Roaming\.minecraft\mods (42 JARs scanned)

[CRITICAL] Missing Required Dependency:
  - 'iris-1.8.0.jar' requires 'sodium' (>=0.6.0), but no sodium mod was found.
  -> Solution: Download Sodium 0.6.0+ for Fabric 1.21.1.

[WARNING] Duplicate Mod Versions Detected:
  - 'cloth-config-15.0.127.jar' (v15.0.127)
  - 'cloth-config-15.0.130.jar' (v15.0.130)
  -> Solution: Remove the older cloth-config-15.0.127.jar.

[WARNING] Potential Mixin Target Collision:
  - In net.minecraft.client.render.WorldRenderer:
    * iris.mixins.json:WorldRendererMixin
    * replaymod.mixins.json:WorldRendererMixin
  -> Risk: Medium (verify shader compatibility with replay recordings).

Summary: 1 Critical, 2 Warnings, 0 Environment Mismatches.
Result: ❌ FIXES REQUIRED BEFORE LAUNCH.
```

---

## 🧪 Testing

```bash
pytest
```

100% test pass rate across 83 automated unit test suites.

---

## 📄 License

Licensed under the [MIT License](LICENSE).
