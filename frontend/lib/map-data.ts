import type { EquipmentListItem, Site } from "@/types";

export type MapCoordinate = { latitude: number; longitude: number };

export function validCoordinate(latitude: unknown, longitude: unknown): MapCoordinate | null {
  return typeof latitude === "number" && Number.isFinite(latitude) && latitude >= -90 && latitude <= 90 &&
    typeof longitude === "number" && Number.isFinite(longitude) && longitude >= -180 && longitude <= 180
    ? { latitude, longitude }
    : null;
}

export function equipmentCoordinate(asset: EquipmentListItem): MapCoordinate | null {
  return validCoordinate(asset.latest_telemetry?.latitude, asset.latest_telemetry?.longitude) ??
    validCoordinate(asset.site?.latitude, asset.site?.longitude);
}

export function equipmentSites(assets: EquipmentListItem[]): Site[] {
  const sites = new Map<string, Site>();
  for (const asset of assets) {
    if (asset.site && validCoordinate(asset.site.latitude, asset.site.longitude)) sites.set(asset.site.id, asset.site);
  }
  return [...sites.values()].sort((a, b) => a.name.localeCompare(b.name));
}

export function coordinateExtent(coordinates: MapCoordinate[]) {
  if (!coordinates.length) return null;
  return coordinates.reduce((extent, point) => ({
    minLatitude: Math.min(extent.minLatitude, point.latitude),
    maxLatitude: Math.max(extent.maxLatitude, point.latitude),
    minLongitude: Math.min(extent.minLongitude, point.longitude),
    maxLongitude: Math.max(extent.maxLongitude, point.longitude),
  }), {
    minLatitude: coordinates[0].latitude,
    maxLatitude: coordinates[0].latitude,
    minLongitude: coordinates[0].longitude,
    maxLongitude: coordinates[0].longitude,
  });
}
