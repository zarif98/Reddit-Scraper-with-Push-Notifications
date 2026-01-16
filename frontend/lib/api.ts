// Utility to get API URL dynamically based on current browser location
// This allows the frontend to work from any device on the network

// Default API port - can be overridden via localStorage
const DEFAULT_API_PORT = 5040;

export function getApiUrl(): string {
    // Priority 1: Environment variable (for Docker private networks)
    // When NEXT_PUBLIC_API_URL is set, always use it
    if (process.env.NEXT_PUBLIC_API_URL) {
        return process.env.NEXT_PUBLIC_API_URL;
    }

    // Priority 2: In the browser, use the same hostname as the frontend
    if (typeof window !== 'undefined') {
        const hostname = window.location.hostname;

        // Check for custom port in localStorage (for easy configuration)
        const customPort = localStorage.getItem('api_port');
        const port = customPort ? parseInt(customPort) : DEFAULT_API_PORT;

        return `http://${hostname}:${port}`;
    }

    // Server-side fallback (during SSR)
    return 'http://localhost:5001';
}

// Helper to set custom API port (call from browser console if needed)
export function setApiPort(port: number): void {
    if (typeof window !== 'undefined') {
        localStorage.setItem('api_port', port.toString());
        console.log(`API port set to ${port}. Refresh the page.`);
    }
}
