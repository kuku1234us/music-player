// Content script for MusicPlayerDL Audio Chrome Extension

// Listen for message from the context menu
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "getVideoUrl") {
    // Get the current video URL
    let videoUrl = window.location.href;

    // If we're on a YouTube watch page
    if (
      window.location.hostname.includes("youtube.com") &&
      window.location.pathname.includes("/watch")
    ) {
      // Send the URL back to the background script
      sendResponse({ url: videoUrl });
      return true;
    }

    // If we're on a Bilibili video page
    if (
      window.location.hostname.includes("bilibili.com") &&
      (window.location.pathname.includes("/video/") ||
        window.location.href.includes("/BV"))
    ) {
      // Send the URL back to the background script
      sendResponse({ url: videoUrl });
      return true;
    }

    // Not on a video page
    sendResponse({ url: null });
    return true;
  }
});

// This helps with right-clicking on videos
document.addEventListener(
  "contextmenu",
  function (event) {
    // Add a data attribute to help identify video elements
    const videoElement = event.target.closest("video");
    if (videoElement) {
      videoElement.setAttribute("data-musicplayerdl-target", "true");
    }
  },
  true
);
