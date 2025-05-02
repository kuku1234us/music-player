// Background script for MusicPlayerDL Video Chrome Extension

// Create context menu items when extension is installed
chrome.runtime.onInstalled.addListener(() => {
  // Remove any existing menu items
  chrome.contextMenus.removeAll();

  // Create video download option directly at top level
  chrome.contextMenus.create({
    id: "video-download",
    title: "Video MusicPlayerDL",
    contexts: ["video", "link"],
    documentUrlPatterns: ["*://*.youtube.com/*", "*://*.bilibili.com/*"],
  });
});

// Handle context menu clicks
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "video-download") {
    const videoUrl = info.linkUrl || info.pageUrl;
    downloadVideo(videoUrl, tab.id);
  }
});

// Handle toolbar icon clicks
chrome.action.onClicked.addListener((tab) => {
  // Check if we're on a supported site
  if (tab.url.includes("youtube.com") || tab.url.includes("bilibili.com")) {
    // Get the current URL and clean it
    downloadVideo(tab.url, tab.id);
  }
});

// Function to download a video
function downloadVideo(url, tabId) {
  // Cleanse the URL to extract video ID
  let cleanUrl = cleanseUrl(url);

  if (cleanUrl) {
    // Format for video download using the musicplayerdl protocol
    const protocolUrl = `musicplayerdl://video/${encodeURIComponent(cleanUrl)}`;

    // Launch the application with the URL
    chrome.tabs.update(tabId, { url: protocolUrl });
  }
}

// Function to cleanse URLs and extract video IDs
function cleanseUrl(url) {
  try {
    // For YouTube URLs
    if (url.includes("youtube.com")) {
      const urlObj = new URL(url);
      const videoId = urlObj.searchParams.get("v");

      if (videoId) {
        return `https://www.youtube.com/watch?v=${videoId}`;
      }
    }

    // For YouTu.be short URLs
    if (url.includes("youtu.be")) {
      const urlObj = new URL(url);
      const videoId = urlObj.pathname.substring(1); // Remove the leading slash

      if (videoId) {
        return `https://www.youtube.com/watch?v=${videoId}`;
      }
    }

    // For Bilibili URLs
    if (url.includes("bilibili.com")) {
      const urlObj = new URL(url);

      // Match BV ID pattern
      const bvMatch = url.match(/\/(?:video\/|)([bB][vV][a-zA-Z0-9]+)/);
      if (bvMatch && bvMatch[1]) {
        return `https://www.bilibili.com/video/${bvMatch[1]}`;
      }
    }

    // If no patterns match, return the original URL
    return url;
  } catch (e) {
    console.error("Error cleansing URL:", e);
    return url;
  }
}

// Listen for messages from content script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "downloadVideo" && message.url) {
    downloadVideo(message.url, sender.tab.id);
  }
});
