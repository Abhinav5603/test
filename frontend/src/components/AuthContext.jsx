import React, { createContext, useState, useEffect, useContext } from 'react';

const AuthContext = createContext();

// Use local backend URL for development
const API_BASE_URL = 'https://test-qccn.onrender.com';

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isLocalMode, setIsLocalMode] = useState(false);

  // Check if user is already logged in on load
  useEffect(() => {
    const checkAuth = async () => {
      try {
        // First, check if the server is in local mode
        const healthResponse = await fetch(`${API_BASE_URL}/api/health`, {
          method: 'GET',
        });
        
        if (healthResponse.ok) {
          const healthData = await healthResponse.json();
          const isLocal = healthData.mode === 'local_development';
          setIsLocalMode(isLocal);
          
          if (isLocal) {
            // In local mode, use the local profile endpoint
            try {
              const localResponse = await fetch(`${API_BASE_URL}/api/profile-local`, {
                method: 'GET',
              });
              
              if (localResponse.ok) {
                const userData = await localResponse.json();
                setUser(userData);
              }
            } catch (localErr) {
              console.log('Local mode - no auth required');
            }
          } else {
            // In production mode, use the regular auth check
            const response = await fetch(`${API_BASE_URL}/api/profile`, {
              method: 'GET',
              credentials: 'include', // Important for cookies
            });

            if (response.ok) {
              const userData = await response.json();
              setUser(userData);
            }
          }
        }
      } catch (err) {
        console.error('Auth check error:', err);
        setError('Cannot connect to server. Please make sure the backend is running.');
      } finally {
        setLoading(false);
      }
    };

    checkAuth();
  }, []);

  // Login function
  const login = async (email, password) => {
    setError(null);
    
    if (isLocalMode) {
      setError('Login not available in local development mode');
      return;
    }
    
    try {
      const response = await fetch(`${API_BASE_URL}/api/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include', // Important for cookies
        body: JSON.stringify({ email, password }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.message || 'Login failed');
      }

      setUser(data.user);
      return data;
    } catch (err) {
      const errorMessage = err.message || 'Network error - please check if backend is running';
      setError(errorMessage);
      throw new Error(errorMessage);
    }
  };

  // Register function
  const register = async (username, email, password) => {
    setError(null);
    
    if (isLocalMode) {
      setError('Registration not available in local development mode');
      return;
    }
    
    try {
      const response = await fetch(`${API_BASE_URL}/api/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, email, password }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.message || 'Registration failed');
      }

      return data;
    } catch (err) {
      const errorMessage = err.message || 'Network error - please check if backend is running';
      setError(errorMessage);
      throw new Error(errorMessage);
    }
  };

  // Logout function
  const logout = async () => {
    try {
      if (!isLocalMode) {
        await fetch(`${API_BASE_URL}/api/logout`, {
          method: 'POST',
          credentials: 'include',
        });
      }
      setUser(null);
    } catch (err) {
      console.error('Logout error:', err);
      // Still set user to null even if logout request fails
      setUser(null);
    }
  };

  const value = {
    user,
    loading,
    error,
    login,
    logout,
    register,
    isLocalMode,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => useContext(AuthContext);

export default AuthContext;