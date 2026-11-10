import unittest
from unittest.mock import patch
from scripts import launch


class LauncherTests(unittest.TestCase):
    def test_existing_server_opens_page_without_starting_another(self):
        with patch.object(launch, 'ready', return_value=True), patch.object(launch.subprocess, 'Popen') as start, patch.object(launch.subprocess, 'run') as browser:
            launch.launch()
        start.assert_not_called()
        browser.assert_called_once_with(['/usr/bin/open', launch.URL], check=True, timeout=15)

    def test_menu_bar_can_start_worker_without_opening_browser(self):
        with patch.object(launch, 'ready', return_value=True), patch.object(launch.subprocess, 'run') as browser:
            launch.launch(open_browser=False)
        browser.assert_not_called()

    def test_cold_start_waits_for_server_then_opens_page(self):
        with patch.object(launch, 'ready', side_effect=[False, False, True]), patch.object(launch.subprocess, 'Popen') as start, patch.object(launch.subprocess, 'run') as browser, patch.object(launch.time, 'sleep'):
            launch.launch()
        self.assertIn('--no-browser', start.call_args.args[0])
        self.assertTrue(start.call_args.kwargs['start_new_session'])
        browser.assert_called_once()

    def test_failed_start_does_not_open_dead_page(self):
        with patch.object(launch, 'ready', return_value=False), patch.object(launch.subprocess, 'Popen'), patch.object(launch.subprocess, 'run') as browser, patch.object(launch.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'server did not start'):
                launch.launch()
        browser.assert_not_called()

if __name__ == '__main__':
    unittest.main()
