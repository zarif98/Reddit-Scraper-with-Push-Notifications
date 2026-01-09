// Utility to get API URL dynamically based on current browser location
// This allows the frontend to work from any device on the network

export function getApiUrl(): string {
    // In the browser, use the same hostname as the frontend but with API port
    if (typeof window !== 'undefined') {
        const hostname = window.location.hostname;
        // If accessing via localhost, use localhost; otherwise use the actual hostname/IP
        return `http://${hostname}:5001`;
    }

    // Server-side fallback (during SSR)
    return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001';
}
