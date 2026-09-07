export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8001';

export async function fetchApi(endpoint: string, options: RequestInit = {}) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    // Skips the ngrok free-tier browser-warning interstitial so API responses
    // come back as JSON, not HTML (harmless / ignored on any other host).
    'ngrok-skip-browser-warning': 'true',
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // Remove Content-Type if it's FormData (browser will set it with boundary automatically)
  if (options.body instanceof FormData) {
    delete headers['Content-Type'];
  }

  const url = `${API_BASE_URL}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;
  
  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    if (response.status === 401 && typeof window !== 'undefined') {
       // Clear token and redirect if Unauthorized
       localStorage.removeItem('token');
       if (window.location.pathname !== '/login') {
         window.location.href = '/login';
       }
    }
    const errorData = await response.json().catch(() => null);
    throw new Error(errorData?.detail || `API Error: ${response.statusText}`);
  }

  if (response.status === 204) {
    return null;
  }
  
  const contentType = response.headers.get('content-type');
  if (contentType && (
    contentType.includes('application/vnd') ||
    contentType.includes('text/csv') ||
    contentType.includes('audio/') ||
    contentType.includes('video/') ||
    contentType.includes('application/octet-stream')
  )) {
      return response.blob();
  }

  return response.json();
}
