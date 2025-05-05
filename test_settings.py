#!/usr/bin/env python
"""
Test script for YouTube download options refactoring.
Tests YtDlpModel presets, resolution handling, codec selection, and the YoutubePage.auto_add_download method.
"""
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Add the project root directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the modules we need to test
from music_player.models.Yt_DlpModel import YtDlpModel
from music_player.ui.pages.youtube_page import YoutubePage
from qt_base_app.models.settings_manager import SettingsManager, SettingType

class TestYtDlpModelPresets(unittest.TestCase):
    """Test cases for YtDlpModel presets and format string generation."""

    def test_audio_preset(self):
        """Test that audio_default preset returns correct options."""
        options = YtDlpModel.get_preset_options("audio_default")
        
        # Verify options exist and have correct format
        self.assertIsNotNone(options)
        self.assertIn('format', options)
        self.assertTrue(options['format'].startswith('bestaudio'))
        
        # Verify merge format is set correctly
        self.assertEqual(options.get('merge_output_format'), 'm4a')

    def test_video_720p_preset(self):
        """Test that video_720p_default preset returns correct options with AVC codec."""
        options = YtDlpModel.get_preset_options("video_720p_default")
        
        # Verify options exist and have correct format
        self.assertIsNotNone(options)
        self.assertIn('format', options)
        
        # Check resolution and codec constraints
        format_str = options['format']
        self.assertIn('height<=720', format_str)
        self.assertIn('vcodec^=avc', format_str)  # Verify AVC codec preference
        
        # Verify merge format is set correctly for video
        self.assertEqual(options.get('merge_output_format'), 'mp4')

    def test_best_video_preset(self):
        """Test that best_video_default preset returns correct options without codec restrictions."""
        options = YtDlpModel.get_preset_options("best_video_default")
        
        # Verify options exist and have correct format
        self.assertIsNotNone(options)
        self.assertIn('format', options)
        
        # Check format string doesn't restrict resolution and doesn't restrict to AVC
        format_str = options['format']
        self.assertIn('bestvideo', format_str)
        self.assertNotIn('height<=', format_str)  # No height restriction
        self.assertNotIn('vcodec^=avc', format_str)  # No AVC codec restriction
        
        # Verify merge format is set correctly for video
        self.assertEqual(options.get('merge_output_format'), 'mp4')

    def test_unknown_preset(self):
        """Test that unknown preset names return an empty dictionary."""
        options = YtDlpModel.get_preset_options("nonexistent_preset")
        self.assertEqual(options, {})

    def test_resolution_handling(self):
        """Test the resolution handling for both portrait and landscape videos."""
        # Test with 720p resolution specified
        options_720p = YtDlpModel.generate_format_string(
            resolution=720,
            use_https=True,
            use_m4a=True
        )
        
        # Verify format string uses height-based selection
        format_str = options_720p['format']
        self.assertIn('height<=720', format_str)
        
        # Verify the new implementation doesn't use width constraints
        self.assertNotIn('width', format_str)

    def test_codec_selection_avc(self):
        """Test that prefer_avc parameter correctly selects AVC codec."""
        options = YtDlpModel.generate_format_string(
            resolution=720,
            prefer_avc=True
        )
        
        # Verify format string has AVC codec preference
        format_str = options['format']
        self.assertIn('vcodec^=avc', format_str)
        
        # Should NOT have the AV1 exclusion when AVC is explicitly preferred
        self.assertNotIn('vcodec!*=av01', format_str)

    def test_codec_selection_exclude_av1(self):
        """Test that AV1 codec is excluded by default for compatibility."""
        options = YtDlpModel.generate_format_string(
            resolution=720,
            prefer_avc=False
        )
        
        # Verify format string excludes AV1 codec
        format_str = options['format']
        self.assertIn('vcodec!*=av01', format_str)

    def test_best_video_no_codec_restriction(self):
        """Test that best video option doesn't restrict codecs by default."""
        options = YtDlpModel.generate_format_string(
            resolution=None,
            prefer_best_video=True
        )
        
        # Verify no codec restrictions are applied
        format_str = options['format']
        self.assertNotIn('vcodec!*=av01', format_str)
        self.assertNotIn('vcodec^=avc', format_str)


class TestYoutubePageAutoAddDownload(unittest.TestCase):
    """Test cases for YoutubePage.auto_add_download method."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create mocks for dependencies
        self.settings_mock = MagicMock()
        self.logger_mock = MagicMock()
        self.download_manager_mock = MagicMock()
        self.video_input_mock = MagicMock()
        
        # Setup patches
        self.settings_patch = patch('qt_base_app.models.settings_manager.SettingsManager.instance', 
                                    return_value=self.settings_mock)
        self.logger_patch = patch('qt_base_app.models.logger.Logger.instance', 
                                  return_value=self.logger_mock)
        
        # Start patches
        self.settings_mock = self.settings_patch.start()
        self.logger_mock = self.logger_patch.start()
        
        # Create YoutubePage instance with mocked dependencies
        with patch('music_player.ui.pages.youtube_page.DownloadManager', return_value=self.download_manager_mock):
            self.youtube_page = YoutubePage()
            self.youtube_page.video_input = self.video_input_mock
            self.youtube_page.download_manager = self.download_manager_mock
    
    def tearDown(self):
        """Tear down test fixtures."""
        # Stop patches
        self.settings_patch.stop()
        self.logger_patch.stop()
    
    @patch('music_player.models.Yt_DlpModel.YtDlpModel.get_preset_options')
    def test_auto_add_download_audio(self, mock_get_preset_options):
        """Test auto_add_download with audio format type."""
        # Setup mock returns
        mock_preset_options = {'format': 'bestaudio'}
        mock_get_preset_options.return_value = mock_preset_options
        self.settings_mock.get.return_value = "/valid/path"
        
        # Mock os.path.isdir to return True
        with patch('os.path.isdir', return_value=True):
            # Call the method
            self.youtube_page.auto_add_download("https://youtube.com/watch?v=test", "audio")
            
            # Verify set_url was called
            self.video_input_mock.set_url.assert_called_once_with("https://youtube.com/watch?v=test")
            
            # Verify get_preset_options was called with correct preset
            mock_get_preset_options.assert_called_once_with("audio_default")
            
            # Verify add_download was called with correct arguments
            self.download_manager_mock.add_download.assert_called_once_with(
                "https://youtube.com/watch?v=test", 
                mock_preset_options,
                "/valid/path"
            )
    
    @patch('music_player.models.Yt_DlpModel.YtDlpModel.get_preset_options')
    def test_auto_add_download_video(self, mock_get_preset_options):
        """Test auto_add_download with video format type."""
        # Setup mock returns
        mock_preset_options = {'format': 'bestvideo[height<=720]'}
        mock_get_preset_options.return_value = mock_preset_options
        self.settings_mock.get.return_value = "/valid/path"
        
        # Mock os.path.isdir to return True
        with patch('os.path.isdir', return_value=True):
            # Call the method
            self.youtube_page.auto_add_download("https://youtube.com/watch?v=test", "video")
            
            # Verify get_preset_options was called with correct preset
            mock_get_preset_options.assert_called_once_with("video_720p_default")
            
            # Verify add_download was called with correct arguments
            self.download_manager_mock.add_download.assert_called_once_with(
                "https://youtube.com/watch?v=test", 
                mock_preset_options,
                "/valid/path"
            )
    
    @patch('music_player.models.Yt_DlpModel.YtDlpModel.get_preset_options')
    def test_auto_add_download_best_video(self, mock_get_preset_options):
        """Test auto_add_download with best-video format type."""
        # Setup mock returns
        mock_preset_options = {'format': 'bestvideo'}
        mock_get_preset_options.return_value = mock_preset_options
        self.settings_mock.get.return_value = "/valid/path"
        
        # Mock os.path.isdir to return True
        with patch('os.path.isdir', return_value=True):
            # Call the method
            self.youtube_page.auto_add_download("https://youtube.com/watch?v=test", "best-video")
            
            # Verify get_preset_options was called with correct preset
            mock_get_preset_options.assert_called_once_with("best_video_default")
            
            # Verify add_download was called with correct arguments
            self.download_manager_mock.add_download.assert_called_once_with(
                "https://youtube.com/watch?v=test", 
                mock_preset_options,
                "/valid/path"
            )
    
    @patch('music_player.models.Yt_DlpModel.YtDlpModel.get_preset_options')
    def test_auto_add_download_invalid_format(self, mock_get_preset_options):
        """Test auto_add_download with invalid format type."""
        # Call the method with invalid format type
        self.youtube_page.auto_add_download("https://youtube.com/watch?v=test", "invalid-format")
        
        # Verify get_preset_options was not called
        mock_get_preset_options.assert_not_called()
        
        # Verify add_download was not called
        self.download_manager_mock.add_download.assert_not_called()
    
    @patch('music_player.models.Yt_DlpModel.YtDlpModel.get_preset_options')
    def test_auto_add_download_invalid_directory(self, mock_get_preset_options):
        """Test auto_add_download with invalid output directory."""
        # Setup mock returns
        mock_preset_options = {'format': 'bestaudio'}
        mock_get_preset_options.return_value = mock_preset_options
        self.settings_mock.get.return_value = "/invalid/path"
        
        # Mock os.path.isdir to return False
        with patch('os.path.isdir', return_value=False):
            # Call the method
            self.youtube_page.auto_add_download("https://youtube.com/watch?v=test", "audio")
            
            # Verify get_preset_options was called
            mock_get_preset_options.assert_called_once_with("audio_default")
            
            # Verify add_download was not called due to invalid directory
            self.download_manager_mock.add_download.assert_not_called()


def run_tests():
    """Run the tests with a test runner."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test cases
    suite.addTests(loader.loadTestsFromTestCase(TestYtDlpModelPresets))
    suite.addTests(loader.loadTestsFromTestCase(TestYoutubePageAutoAddDownload))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


def main():
    """Run the test script."""
    print("Running YouTube Download Options Refactoring Tests")
    print("=" * 60)
    
    success = run_tests()
    
    print("=" * 60)
    status = "PASSED" if success else "FAILED"
    print(f"Test Suite {status}")
    
    # Exit with appropriate status code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main() 