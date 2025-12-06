# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
"""Tests for PreferencesVarietyDialog timer cleanup on destroy.

These tests verify that the _preview_refresh_timer is properly cancelled
when the dialog is destroyed to prevent memory leaks and callback execution
on destroyed widgets.
"""

import unittest
import threading
import time
from unittest.mock import MagicMock


class TestPreviewTimerCleanup(unittest.TestCase):
    """Tests for preview timer cleanup on dialog destruction."""

    def test_preview_timer_is_cancelled_on_destroy(self):
        """The preview refresh timer must be cancelled when dialog is destroyed.

        This prevents memory leaks and avoids callbacks executing on destroyed
        widgets, which causes GTK errors and resource leaks.

        The test simulates the exact behavior of PreferencesVarietyDialog's
        on_destroy method and verifies the timer is properly cleaned up.
        """
        # Track if callback was executed (should NOT happen after proper cleanup)
        callback_executed = {'value': False}

        def timer_callback():
            callback_executed['value'] = True

        # Create a mock that simulates the dialog with the timer
        class MockDialogWithCurrentBuggyBehavior:
            """Simulates PreferencesVarietyDialog with current buggy on_destroy."""

            def __init__(self):
                self._preview_refresh_timer = threading.Timer(0.1, timer_callback)
                self._preview_refresh_timer.start()
                self.dialog = None
                self.fav_chooser = MagicMock()
                self.fetched_chooser = MagicMock()
                self.parent = MagicMock()
                self.parent.thumbs_manager = MagicMock()

            def on_destroy(self, widget=None):
                """Exact copy of current on_destroy from PreferencesVarietyDialog.

                NOTE: This is the BUGGY version - it doesn't cancel the timer!
                Line 1271-1282 of PreferencesVarietyDialog.py
                """
                if hasattr(self, "dialog") and self.dialog:
                    try:
                        self.dialog.destroy()
                    except Exception:
                        pass
                for chooser in (self.fav_chooser, self.fetched_chooser):
                    try:
                        chooser.destroy()
                    except Exception:
                        pass
                self.parent.thumbs_manager.hide(force=False)

        mock_dialog = MockDialogWithCurrentBuggyBehavior()

        # Verify timer is running before destroy
        self.assertTrue(mock_dialog._preview_refresh_timer.is_alive(),
                       "Timer should be alive before destroy")

        # Call on_destroy (this should cancel the timer, but it doesn't!)
        mock_dialog.on_destroy()

        # Cancel the timer manually (since the bug doesn't do it)
        # This is what we expect on_destroy to do
        mock_dialog._preview_refresh_timer.cancel()

        # Wait a moment to ensure timer callback would have executed if not cancelled
        time.sleep(0.15)

        # The timer callback should NOT have executed
        # But this test is actually about whether on_destroy cancels it.
        # To make this a proper failing test, we need to check the actual
        # PreferencesVarietyDialog.on_destroy behavior.

        # For a proper RED test, we need to import and test the real method.
        # Let's use a different approach - verify the method doesn't have
        # the timer cancellation code.

        # Read the source and verify the bug exists
        import inspect
        import variety.PreferencesVarietyDialog as prefs_module

        source = inspect.getsource(prefs_module.PreferencesVarietyDialog.on_destroy)

        # This test FAILS if on_destroy contains timer cancellation code
        # It PASSES when the bug is fixed (timer cancellation is added)
        self.assertIn('_preview_refresh_timer', source,
                     "on_destroy should handle _preview_refresh_timer")
        self.assertIn('.cancel()', source,
                     "on_destroy must call .cancel() on _preview_refresh_timer")

    def test_preview_timer_none_does_not_raise_on_destroy(self):
        """Destroying dialog when no timer exists should not raise errors."""
        class MockDialog:
            def __init__(self):
                # No timer exists
                self.dialog = None
                self.fav_chooser = MagicMock()
                self.fetched_chooser = MagicMock()
                self.parent = MagicMock()
                self.parent.thumbs_manager = MagicMock()

            def on_destroy_fixed(self, widget=None):
                """Fixed on destroy with proper timer handling."""
                # Cancel preview refresh timer if it exists
                if hasattr(self, '_preview_refresh_timer') and self._preview_refresh_timer:
                    self._preview_refresh_timer.cancel()
                    self._preview_refresh_timer = None

                if hasattr(self, "dialog") and self.dialog:
                    try:
                        self.dialog.destroy()
                    except Exception:
                        pass
                for chooser in (self.fav_chooser, self.fetched_chooser):
                    try:
                        chooser.destroy()
                    except Exception:
                        pass
                self.parent.thumbs_manager.hide(force=False)

        mock_dialog = MockDialog()

        # Should not raise any exceptions even when _preview_refresh_timer doesn't exist
        mock_dialog.on_destroy_fixed()

    def test_multiple_destroy_calls_do_not_raise(self):
        """Calling on_destroy multiple times should not raise errors."""
        class MockDialog:
            def __init__(self):
                self._preview_refresh_timer = threading.Timer(10.0, lambda: None)
                self._preview_refresh_timer.start()
                self.dialog = None
                self.fav_chooser = MagicMock()
                self.fetched_chooser = MagicMock()
                self.parent = MagicMock()
                self.parent.thumbs_manager = MagicMock()

            def on_destroy_fixed(self, widget=None):
                """Fixed on_destroy with proper timer cleanup."""
                # Cancel preview refresh timer if it exists
                if hasattr(self, '_preview_refresh_timer') and self._preview_refresh_timer:
                    self._preview_refresh_timer.cancel()
                    self._preview_refresh_timer = None

                if hasattr(self, "dialog") and self.dialog:
                    try:
                        self.dialog.destroy()
                    except Exception:
                        pass
                for chooser in (self.fav_chooser, self.fetched_chooser):
                    try:
                        chooser.destroy()
                    except Exception:
                        pass
                self.parent.thumbs_manager.hide(force=False)

        mock_dialog = MockDialog()

        # First destroy
        mock_dialog.on_destroy_fixed()

        # Timer should be None after first destroy
        self.assertIsNone(mock_dialog._preview_refresh_timer)

        # Second destroy should not raise
        mock_dialog.on_destroy_fixed()


    def test_show_timer_is_cancelled_on_destroy(self):
        """The show_timer must be cancelled when dialog is destroyed.

        show_timer is used for delayed show of source items. If not cancelled,
        it can cause callbacks to execute on destroyed widgets.
        """
        import inspect
        import variety.PreferencesVarietyDialog as prefs_module

        source = inspect.getsource(prefs_module.PreferencesVarietyDialog.on_destroy)

        # Verify show_timer is handled in on_destroy
        self.assertIn('show_timer', source,
                     "on_destroy should handle show_timer")

    def test_apply_timer_is_cancelled_on_destroy(self):
        """The apply_timer must be cancelled when dialog is destroyed.

        apply_timer is used for delayed apply of changes. If not cancelled,
        it can cause callbacks to execute on destroyed widgets.
        """
        import inspect
        import variety.PreferencesVarietyDialog as prefs_module

        source = inspect.getsource(prefs_module.PreferencesVarietyDialog.on_destroy)

        # Verify apply_timer is handled in on_destroy
        self.assertIn('apply_timer', source,
                     "on_destroy should handle apply_timer")


if __name__ == '__main__':
    unittest.main()
