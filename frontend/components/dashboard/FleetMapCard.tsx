"use client";

import React, { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import mapboxgl from "mapbox-gl";
import { Navigation } from "lucide-react";
import { GlassCard } from "../ui/GlassCard";
import { SITE_COORDINATES, STATUS_CONFIG } from "@/lib/constants";
import { EquipmentListItem, EquipmentStatus } from "@/types";
import { cn } from "@/lib/utils";

interface FleetMapCardProps {
  equipmentList: EquipmentListItem[];
}

export function FleetMapCard({ equipmentList }: FleetMapCardProps) {
  const router = useRouter();
  const [selectedSiteId, setSelectedSiteId] = useState<string>("ALL");
  const mapboxToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;
  const hasMapboxToken = Boolean(mapboxToken?.trim());
  const [mapboxError, setMapboxError] = useState<boolean>(false);
  const [isMapReady, setIsMapReady] = useState<boolean>(false);

  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const markersRef = useRef<Map<string, { marker: mapboxgl.Marker; element: HTMLElement; popup: mapboxgl.Popup }>>(new Map());

  const filteredAssets = selectedSiteId === "ALL"
    ? equipmentList
    : equipmentList.filter((eq) => eq.site?.id === selectedSiteId);

  // 1. Initialize Mapbox GL Instance
  useEffect(() => {
    if (!mapboxToken || mapboxToken.trim() === "") {
      return;
    }

    if (!mapContainerRef.current) return;

    try {
      mapboxgl.accessToken = mapboxToken!;

      const map = new mapboxgl.Map({
        container: mapContainerRef.current,
        style: "mapbox://styles/mapbox/dark-v11",
        center: [77.5, 17.5],
        zoom: 4.8,
        attributionControl: false,
        cooperativeGestures: false,
      });

      // Track immediately so navigating away before load still releases WebGL resources.
      mapRef.current = map;
      map.on("load", () => {
        setIsMapReady(true);
      });

      map.on("error", (e) => {
        console.warn("Mapbox GL runtime warning/error:", e);
        if (e.error && (e.error.message?.includes("forbidden") || e.error.message?.includes("unauthorized") || e.error.message?.includes("Invalid Token"))) {
          setMapboxError(true);
        }
      });
    } catch (err) {
      console.warn("Failed to initialize Mapbox:", err);
      queueMicrotask(() => setMapboxError(true));
    }

    return () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, [hasMapboxToken, mapboxToken]);

  // 2. Synchronize Live Equipment Markers upon Telemetry Updates (SSE)
  useEffect(() => {
    if (!mapRef.current || !isMapReady) return;

    const map = mapRef.current;

    filteredAssets.forEach((asset) => {
      const lat = asset.latest_telemetry?.latitude ?? (asset.site ? asset.site.latitude : 18.7180);
      const lng = asset.latest_telemetry?.longitude ?? (asset.site ? asset.site.longitude : 81.2580);
      const status = asset.status || "UNASSIGNED";
      const normStatus = (STATUS_CONFIG[status as EquipmentStatus] ? status : "UNASSIGNED") as EquipmentStatus;
      const color = STATUS_CONFIG[normStatus].color;

      if (markersRef.current.has(asset.id)) {
        const item = markersRef.current.get(asset.id)!;
        item.marker.setLngLat([lng, lat]);
      } else {
        const el = document.createElement("div");
        el.className = "cursor-pointer group relative";
        el.innerHTML = `
          <div style="position: relative; display: flex; align-items: center; justify-content: center;">
            <div style="position: absolute; width: 22px; height: 22px; border-radius: 9999px; background: ${color}; opacity: 0.25; animation: ping 2s cubic-bezier(0, 0, 0.2, 1) infinite;"></div>
            <div style="width: 12px; height: 12px; border-radius: 9999px; background: ${color}; border: 2px solid #ffffff; box-shadow: 0 2px 4px rgba(0,0,0,0.5);"></div>
            <span style="position: absolute; bottom: -16px; font-size: 8px; font-weight: 700; color: #ffffff; background: #000000; padding: 1px 4px; border-radius: 3px; border: 1px solid rgba(255,255,255,0.2); white-space: nowrap;">
              ${asset.id}
            </span>
          </div>
        `;

        el.addEventListener("click", () => {
          router.push(`/assets/${asset.id}`);
        });

        const popupHtml = `
          <div style="font-family: sans-serif; padding: 4px; color: #ffffff; min-width: 140px;">
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.15); padding-bottom: 4px; margin-bottom: 6px;">
              <strong style="color: #ff5a24; font-size: 12px; font-weight: 700;">${asset.id}</strong>
              <span style="font-size: 10px; color: rgba(255,255,255,0.7); font-weight: 500;">${asset.type}</span>
            </div>
            <div style="font-size: 11px; line-height: 1.5; color: #dddddd;">
              <div><span style="color: rgba(255,255,255,0.6);">Status:</span> <strong style="color: ${color};">${STATUS_CONFIG[normStatus].label}</strong></div>
              <div><span style="color: rgba(255,255,255,0.6);">Site:</span> ${asset.site?.name || "Depot Yard"}</div>
              <div><span style="color: rgba(255,255,255,0.6);">GPS:</span> ${lat.toFixed(4)}, ${lng.toFixed(4)}</div>
            </div>
          </div>
        `;

        const popup = new mapboxgl.Popup({
          offset: 14,
          className: "rentsense-map-popup",
          closeButton: false,
          closeOnClick: false,
          focusAfterOpen: false,
        }).setHTML(popupHtml);

        const marker = new mapboxgl.Marker({
          element: el,
          anchor: "center",
        })
          .setLngLat([lng, lat])
          .setPopup(popup)
          .addTo(map);

        markersRef.current.set(asset.id, { marker, element: el, popup });
      }
    });
  }, [filteredAssets, isMapReady, router]);

  const handleSiteSelect = (siteId: string) => {
    setSelectedSiteId(siteId);

    if (mapRef.current) {
      if (siteId === "ALL") {
        mapRef.current.flyTo({
          center: [77.5, 17.5],
          zoom: 4.8,
          speed: 1.2,
          curve: 1.4,
          essential: true,
        });
      } else {
        const targetSite = SITE_COORDINATES.find((s) => s.id === siteId);
        if (targetSite) {
          mapRef.current.flyTo({
            center: [targetSite.lng, targetSite.lat],
            zoom: 14.2,
            speed: 1.2,
            curve: 1.4,
            essential: true,
          });
        }
      }
    }
  };

  const handleCenterFleet = () => {
    setSelectedSiteId("ALL");
    if (mapRef.current) {
      if (filteredAssets.length > 0) {
        const bounds = new mapboxgl.LngLatBounds();
        filteredAssets.forEach((asset) => {
          const lat = asset.latest_telemetry?.latitude ?? (asset.site ? asset.site.latitude : 18.7180);
          const lng = asset.latest_telemetry?.longitude ?? (asset.site ? asset.site.longitude : 81.2580);
          bounds.extend([lng, lat]);
        });
        mapRef.current.fitBounds(bounds, { padding: 60, maxZoom: 14 });
      } else {
        mapRef.current.flyTo({
          center: [77.5, 17.5],
          zoom: 4.8,
          speed: 1.2,
        });
      }
    }
  };

  const minLat = 12.0;
  const maxLat = 21.0;
  const minLng = 71.0;
  const maxLng = 83.5;

  const projectCoord = (lat: number, lng: number) => {
    const x = ((lng - minLng) / (maxLng - minLng)) * 100;
    const y = (1 - (lat - minLat) / (maxLat - minLat)) * 100;
    return {
      left: `${Math.min(92, Math.max(8, x))}%`,
      top: `${Math.min(88, Math.max(12, y))}%`,
    };
  };

  const useFallbackMap = !hasMapboxToken || mapboxError;

  return (
    <GlassCard variant="light" className="p-7 overflow-hidden relative flex flex-col justify-between">
      {/* Card Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 z-10">
        <div>
          <div className="flex items-center gap-2">
            <span className="size-2 bg-[#ff5a24] shadow-[0_0_0_1px_rgba(255,90,36,0.2)]" />
            <h3 className="text-xs font-semibold uppercase tracking-wider text-black">
              Tactical Fleet Map
            </h3>
            {useFallbackMap ? (
              <span className="text-[10px] font-mono text-[#ff5a24] bg-[#ff5a24]/10 border border-[#ff5a24]/20 px-2 py-0.5 rounded-full">
                Tactical Vector Mode
              </span>
            ) : (
              <span className="text-[10px] font-mono text-emerald-700 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full flex items-center gap-1">
                <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse" />
                Mapbox Geographic Base
              </span>
            )}
          </div>
          <p className="text-xs text-[#6a6a6a] mt-0.5">
            Realtime telemetry stream &amp; live GPS coordinates
          </p>
        </div>

        {/* Site Filter Tabs */}
        <div className="flex items-center gap-1.5 rounded-xl border border-black/10 bg-white/70 p-1 text-xs shadow-sm">
          <button
            onClick={() => handleSiteSelect("ALL")}
            className={cn(
              "px-3 py-1 rounded-lg font-medium transition-all",
              selectedSiteId === "ALL"
                ? "bg-[#111111] text-white shadow-sm"
                : "text-[#555] hover:text-black"
            )}
          >
            All Sites ({equipmentList.length})
          </button>
          {SITE_COORDINATES.map((site) => (
            <button
              key={site.id}
              onClick={() => handleSiteSelect(site.id)}
              className={cn(
                "px-3 py-1 rounded-lg font-medium transition-all hidden md:block",
                selectedSiteId === site.id
                  ? "bg-[#111111] text-white shadow-sm"
                  : "text-[#555] hover:text-black"
              )}
            >
              {site.name.split(" ")[0]}
            </button>
          ))}
        </div>
      </div>

      {/* Centerpiece Map View Area */}
      <div className="relative my-6 h-80 sm:h-96 w-full rounded-2xl border border-black/15 bg-[#111111] overflow-hidden shadow-inner">
        {/* 1. Real Geographic Base Layer (Mapbox GL Container) */}
        {!useFallbackMap ? (
          <div ref={mapContainerRef} className="absolute inset-0 size-full z-0" />
        ) : (
          /* Fallback Tactical Canvas */
          <div className="absolute inset-0 size-full bg-[#eae7df] z-0 overflow-hidden">
            {/* Vector Background Map Grid & Radial Scan Rings */}
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgba(255,255,255,0.7),transparent_70%)] pointer-events-none" />
            <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(0,0,0,0.05)_1px,transparent_1px),linear-gradient(to_bottom,rgba(0,0,0,0.05)_1px,transparent_1px)] bg-[size:2rem_2rem] opacity-70 pointer-events-none" />

            {/* Fallback Site Landmarks */}
            {SITE_COORDINATES.map((site) => {
              const coords = projectCoord(site.lat, site.lng);
              return (
                <div
                  key={site.id}
                  style={{ left: coords.left, top: coords.top }}
                  className="absolute -translate-x-1/2 -translate-y-1/2 pointer-events-none flex flex-col items-center"
                >
                  <div className="size-16 rounded-full border border-black/10 bg-white/30 backdrop-blur-[2px]" />
                  <span className="text-[10px] font-bold uppercase tracking-wider text-black/70 mt-1 bg-white/80 px-2 py-0.5 rounded shadow-sm border border-black/10">
                    {site.name}
                  </span>
                </div>
              );
            })}

            {/* Fallback Pins */}
            {filteredAssets.map((asset) => {
              const lat = asset.latest_telemetry?.latitude || (asset.site ? 37.7749 : 37.7610);
              const lng = asset.latest_telemetry?.longitude || (asset.site ? -122.4194 : -122.4480);
              const pos = projectCoord(lat, lng);
              const normStatus = (asset.status.toUpperCase() as EquipmentStatus) in STATUS_CONFIG
                ? (asset.status.toUpperCase() as EquipmentStatus)
                : "UNASSIGNED";
              const color = STATUS_CONFIG[normStatus].color;

              return (
                <Link
                  key={asset.id}
                  href={`/assets/${asset.id}`}
                  style={{ left: pos.left, top: pos.top }}
                  className="absolute -translate-x-1/2 -translate-y-1/2 group z-20 transition-all duration-700 ease-out hover:scale-125"
                >
                  <div className="relative flex items-center justify-center">
                    <span
                      className="size-5 rounded-full shadow-lg border-2 border-white flex items-center justify-center transition-all group-hover:ring-4 group-hover:ring-black/10"
                      style={{ backgroundColor: color }}
                    >
                      <span className="size-1.5 rounded-full bg-white animate-pulse" />
                    </span>

                    {/* Tooltip Tag */}
                    <div className="absolute bottom-full mb-2 hidden group-hover:flex flex-col items-center whitespace-nowrap rounded-xl bg-[#111111] px-3 py-2 text-xs text-white shadow-2xl border border-white/20 z-30">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-[#ff5a24]">{asset.id}</span>
                        <span>•</span>
                        <span>{asset.type}</span>
                      </div>
                      <div className="flex items-center gap-2 mt-1 text-[10px] text-white/70">
                        <span>{STATUS_CONFIG[normStatus].label}</span>
                        <span>|</span>
                        <span>{asset.site?.name || "Yard Staging"}</span>
                      </div>
                      <div className="mt-1 text-[9px] font-mono text-white/50">
                        {lat.toFixed(4)}, {lng.toFixed(4)}
                      </div>
                      <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-[#111111]" />
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        )}

        {/* 2. RentSense Tactical Control Tower Overlay (Pointer Events None) */}
        <div className="absolute inset-0 pointer-events-none z-10">
          {/* Tactical Crosshairs & Radar Scanner */}
          <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 size-72 rounded-full border border-white/10" />
          <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 size-48 rounded-full border border-dashed border-white/15" />
          <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 size-24 rounded-full border border-white/10" />
          <div className="absolute left-1/2 top-0 bottom-0 w-px -translate-x-1/2 bg-white/10" />
          <div className="absolute top-1/2 left-0 right-0 h-px -translate-y-1/2 bg-white/10" />

          {/* Spinning Radar Beam */}
          <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 size-72 rounded-full bg-[conic-gradient(from_0deg,transparent_0deg,transparent_270deg,rgba(255,90,36,0.15)_360deg)] animate-radar" />
        </div>

        {/* 3. Map Overlay Controls */}
        <div className="absolute bottom-4 right-4 flex items-center gap-2 z-20">
          <button
            onClick={handleCenterFleet}
            className="flex items-center gap-1.5 rounded-lg border border-black/10 bg-white/90 px-3 py-1.5 text-xs font-medium text-black shadow-sm hover:bg-white transition-colors"
          >
            <Navigation className="size-3 text-[#ff5a24]" />
            <span>Center Fleet</span>
          </button>
        </div>

        {/* 4. Live Status Legend Bar */}
        <div className="absolute bottom-4 left-4 hidden sm:flex items-center gap-3 rounded-lg border border-black/10 bg-white/85 px-3 py-1.5 text-[11px] backdrop-blur shadow-sm z-20">
          <div className="flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-emerald-500" />
            <span className="text-black font-medium">Active</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-amber-500" />
            <span className="text-black font-medium">Idle</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-[#ff5a24]" />
            <span className="text-black font-medium">Due Soon</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-red-600" />
            <span className="text-black font-medium">Overdue</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-slate-400" />
            <span className="text-black font-medium">Unassigned</span>
          </div>
        </div>
      </div>
    </GlassCard>
  );
}
