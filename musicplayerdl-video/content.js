// Listen for right clicks on video elements or links
document.addEventListener(
  "contextmenu",
  function (event) {
    // Check if the clicked element is a video or link to a video
    let target = event.target;
    let videoUrl = null;

    // For video elements
    if (target.tagName === "VIDEO") {
      videoUrl = window.location.href;
    }

    // Store the URL for later use
    if (videoUrl) {
      chrome.storage.local.set({ lastVideoUrl: videoUrl });
    }
  },
  true
);

// Optional: Add custom menu items to the YouTube player
if (window.location.hostname.includes("youtube.com")) {
  window.addEventListener("load", function () {
    // This will run after the page is fully loaded
    setTimeout(enhanceYouTubePlayer, 2000);
  });
}

function enhanceYouTubePlayer() {
  // Try to find the YouTube player
  const player = document.querySelector(".html5-video-player");
  if (!player) return;

  // Create our custom menu button if it doesn't exist
  if (!document.getElementById("ytm-download-button")) {
    const menuContainer = document.querySelector(".ytp-right-controls");
    if (menuContainer) {
      const downloadButton = document.createElement("button");
      downloadButton.id = "ytm-download-button";
      downloadButton.className = "ytp-button";
      downloadButton.title = "Download with YouTubeMaster";
      downloadButton.innerHTML = "↓"; // Simple download icon

      // Style the button
      downloadButton.style.fontSize = "16px";
      downloadButton.style.fontWeight = "bold";

      // Add click handler
      downloadButton.addEventListener("click", function () {
        chrome.runtime.sendMessage({
          action: "downloadVideo",
          url: window.location.href,
        });
      });

      // Add to player controls
      menuContainer.insertBefore(downloadButton, menuContainer.firstChild);
    }
  }
}

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
      videoElement.setAttribute("data-youtubemaster-target", "true");
    }
  },
  true
);
