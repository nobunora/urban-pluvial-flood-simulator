import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import type { ResultMetadataResponse } from "../api/client";
import { resultLayerUrl } from "../api/client";
import { resultBounds, resultImageCoordinates } from "./resultGeometry";

type Props = {
  runId: string;
  metadata: ResultMetadataResponse;
  onInspect: (lon: number, lat: number) => void;
};

export default function ResultMap({ runId, metadata, onInspect }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          gsi: {
            type: "raster",
            tiles: ["https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "国土地理院",
          },
          "result-max-depth": {
            type: "image",
            url: resultLayerUrl(runId, "max-depth"),
            coordinates: resultImageCoordinates(metadata.bounds),
          },
        },
        layers: [
          {
            id: "gsi",
            type: "raster",
            source: "gsi",
          },
          {
            id: "result-max-depth",
            type: "raster",
            source: "result-max-depth",
            paint: {
              "raster-opacity": 0.82,
            },
          },
        ],
      },
      bounds: resultBounds(metadata.bounds),
      fitBoundsOptions: { padding: 32, maxZoom: 18 },
      attributionControl: true,
    });

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    let marker: maplibregl.Marker | null = null;
    const handleClick = (event: maplibregl.MapMouseEvent) => {
      marker?.remove();
      marker = new maplibregl.Marker({ color: "#1f2937" })
        .setLngLat(event.lngLat)
        .addTo(map);
      onInspect(event.lngLat.lng, event.lngLat.lat);
    };
    map.on("click", handleClick);

    return () => {
      marker?.remove();
      map.off("click", handleClick);
      map.remove();
    };
  }, [metadata, onInspect, runId]);

  return (
    <div
      ref={containerRef}
      className="result-map"
      aria-label="最大浸水深の地図"
    />
  );
}
