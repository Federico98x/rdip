'use client';

import { useState, useEffect } from 'react';
import { X, Share, Plus } from 'lucide-react';

export function PWAInstallPrompt() {
  const [showPrompt, setShowPrompt] = useState(false);
  const [isIOS, setIsIOS] = useState(false);
  const [isStandalone, setIsStandalone] = useState(false);

  useEffect(() => {
    const iOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !(window as typeof window & { MSStream?: unknown }).MSStream;
    const standalone = window.matchMedia('(display-mode: standalone)').matches || 
                       (window.navigator as Navigator & { standalone?: boolean }).standalone === true;
    
    setIsIOS(iOS);
    setIsStandalone(standalone);
    
    const dismissed = localStorage.getItem('pwa-install-dismissed');
    const dismissedTime = dismissed ? parseInt(dismissed) : 0;
    const daysSinceDismissed = (Date.now() - dismissedTime) / (1000 * 60 * 60 * 24);
    
    if (iOS && !standalone && daysSinceDismissed > 7) {
      setTimeout(() => setShowPrompt(true), 3000);
    }
  }, []);

  const handleDismiss = () => {
    localStorage.setItem('pwa-install-dismissed', Date.now().toString());
    setShowPrompt(false);
  };

  if (!showPrompt || !isIOS || isStandalone) return null;

  return (
    <div className="fixed bottom-0 inset-x-0 z-[100] p-4 pb-[calc(env(safe-area-inset-bottom)+1rem)] animate-in slide-in-from-bottom duration-300">
      <div className="bg-[#1a1a24] border border-white/10 rounded-2xl p-4 shadow-2xl shadow-black/50 max-w-md mx-auto">
        <div className="flex items-start gap-3">
          <div className="bg-gradient-to-br from-cyan-500 to-blue-600 p-2.5 rounded-xl shrink-0">
            <Plus className="h-5 w-5 text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-white text-sm">Install RDIP</h3>
            <p className="text-slate-400 text-xs mt-1 leading-relaxed">
              Add to your Home Screen for the best experience.
            </p>
            <div className="flex items-center gap-2 mt-3 text-xs text-slate-300">
              <span>Tap</span>
              <Share className="h-4 w-4 text-cyan-400" />
              <span>then &quot;Add to Home Screen&quot;</span>
            </div>
          </div>
          <button 
            onClick={handleDismiss}
            className="p-1.5 rounded-lg hover:bg-white/10 transition-colors"
          >
            <X className="h-4 w-4 text-slate-500" />
          </button>
        </div>
      </div>
    </div>
  );
}
