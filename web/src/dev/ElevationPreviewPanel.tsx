import type { ElevationPreviewResponse } from "../api/client";
import ResultMap from "../result/ResultMap";

type Props = {
  preview: ElevationPreviewResponse;
  onRun: () => void;
  onClose: () => void;
};

export default function ElevationPreviewPanel({ preview, onRun, onClose }: Props) {
  const providerCounts = preview.provider_counts ?? {};
  return (
    <section className="smoke-card elevation-preview" aria-labelledby="elevation-preview-title">
      <div className="elevation-preview-heading">
        <div>
          <p className="smoke-kicker">ELEVATION PREVIEW</p>
          <h2 id="elevation-preview-title">取得した標高</h2>
        </div>
        <button type="button" onClick={onClose}>閉じる</button>
      </div>
      <p>
        {preview.width_samples.toLocaleString()} × {preview.height_samples.toLocaleString()}点 / {preview.grid_cell_size_m} m格子
      </p>
      <div className="elevation-preview-layout">
        <ResultMap
          metadata={{ bounds: preview.bounds }}
          imageUrl={preview.image_url}
          flowVectorData={null}
          flowDisplayMode={null}
          backgroundOpacity={0.55}
          mapLabel="取得した標高の地図"
        />
        <aside className="result-legend elevation-preview-legend" aria-label="取得した標高の凡例">
          <strong>標高 (m)</strong>
          {preview.elevation_legend.map((item) => (
            <span key={item.label}>
              <i style={{ backgroundColor: item.color }} aria-hidden="true" />
              {item.label}
            </span>
          ))}
          {Object.keys(providerCounts).length > 0 && (
            <small>
              取得元: {Object.entries(providerCounts)
                .map(([provider, count]) => `${provider} ${count.toLocaleString()}点`)
                .join(" / ")}
            </small>
          )}
          {preview.nearest_filled_cells > 0 && (
            <small>近傍補完: {preview.nearest_filled_cells.toLocaleString()}点</small>
          )}
          <button type="button" className="analysis-start-button" onClick={onRun}>
            この条件で解析開始
          </button>
        </aside>
      </div>
    </section>
  );
}
