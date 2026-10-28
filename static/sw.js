/* Night Shift owner-phone service worker: show the push, open its URL on tap. Nothing else. */
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (err) {
    data = {};
  }
  const title = typeof data.title === "string" && data.title ? data.title : "Night Shift";
  const body = typeof data.body === "string" ? data.body : "";
  const url = typeof data.url === "string" && data.url ? data.url : "/";
  event.waitUntil(self.registration.showNotification(title, { body, data: { url } }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const data = event.notification.data || {};
  const url = typeof data.url === "string" && data.url ? data.url : "/";
  event.waitUntil(clients.openWindow(url));
});
