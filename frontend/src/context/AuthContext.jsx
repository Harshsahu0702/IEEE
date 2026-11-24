import React, { createContext, useContext, useState, useEffect } from 'react';
import { api } from '../services/api';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [token, setToken] = useState(() => sessionStorage.getItem('omnisense_token'));
  const [user, setUser] = useState(() => {
    try {
      return JSON.parse(sessionStorage.getItem('omnisense_user') || 'null');
    } catch {
      return null;
    }
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Listen for unauthorized 401 events from api client
    const handleUnauthorized = () => {
      logout();
    };
    window.addEventListener('auth:unauthorized', handleUnauthorized);

    // Initial check
    if (token && !user) {
      api.auth.getProfile()
        .then((userData) => {
          setUser(userData);
          sessionStorage.setItem('omnisense_user', JSON.stringify(userData));
        })
        .catch(() => logout())
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }

    return () => {
      window.removeEventListener('auth:unauthorized', handleUnauthorized);
    };
  }, [token]);

  const login = async (username, password) => {
    const data = await api.auth.login(username, password);
    api.setToken(data.access_token, data.user);
    setToken(data.access_token);
    setUser(data.user);
    return data;
  };

  const logout = () => {
    api.clearToken();
    setToken(null);
    setUser(null);
  };

  const isAdmin = user?.role === 'admin';
  const isViewer = user?.role === 'viewer';
  const canOperate = user && user.role !== 'viewer';

  return (
    <AuthContext.Provider
      value={{
        token,
        user,
        loading,
        login,
        logout,
        isAuthenticated: !!token,
        isAdmin,
        isViewer,
        canOperate,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
