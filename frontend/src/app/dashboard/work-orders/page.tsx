"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { PageHeader } from "@/components/ui/states";
import { useScope } from "@/components/dashboard/scope";
import { plantsApi, workOrdersApi } from "@/lib/api";
import type { Plant, WorkOrderRecord } from "@/lib/api";

const COLUMNS = [
  { id: "open", label: "Open", color: "#6b7280" },
  { id: "assigned", label: "Assigned", color: "#3b82f6" },
  { id: "in_progress", label: "In Progress", color: "#f59e0b" },
  { id: "resolved", label: "Resolved", color: "#10b981" },
  { id: "verified", label: "Verified", color: "#2f6b4f" },
] as const;

export default function WorkOrdersPage() {
  const searchParams = useSearchParams();
  const scope = useScope();

  const [plants, setPlants] = useState<Plant[]>([]);
  const [selectedPlantId, setSelectedPlantId] = useState<number | null>(scope.plantId || 1);
  const [workOrders, setWorkOrders] = useState<WorkOrderRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [viewMode, setViewMode] = useState<"kanban" | "list">("kanban");

  const [selectedOrder, setSelectedOrder] = useState<WorkOrderRecord | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState<boolean>(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState<boolean>(false);

  // Drawer edit states
  const [editAssignee, setEditAssignee] = useState<string>("");
  const [editDueDate, setEditDueDate] = useState<string>("");
  const [editResolutionNote, setEditResolutionNote] = useState<string>("");
  const [editAfterPhoto, setEditAfterPhoto] = useState<string>("");
  const [checklist, setChecklist] = useState<Array<{ id: string; text: string; done: boolean }>>([]);
  const [actionError, setActionError] = useState<string | null>(null);
  const [verifyResult, setVerifyResult] = useState<string | null>(null);

  // New Work Order modal state
  const [newPanelId, setNewPanelId] = useState<string>("S-04-MOD12");
  const [newClass, setNewClass] = useState<string>("dusty");
  const [newSeverity, setNewSeverity] = useState<string>("MEDIUM");
  const [newPriority, setNewPriority] = useState<string>("high");
  const [newAssignee, setNewAssignee] = useState<string>("");
  const [newNotes, setNewNotes] = useState<string>("");

  // Sync with scope
  useEffect(() => {
    if (scope.plantId && scope.plantId !== selectedPlantId) {
      setSelectedPlantId(scope.plantId);
    }
  }, [scope.plantId, selectedPlantId]);

  // Load plants
  useEffect(() => {
    plantsApi.list().then((res) => {
      if (res && res.length > 0) {
        setPlants(res);
        if (!selectedPlantId) setSelectedPlantId(res[0].id);
      }
    }).catch(() => {});
  }, [selectedPlantId]);

  // Load work orders
  const loadWorkOrders = () => {
    setLoading(true);
    workOrdersApi
      .list({ plant_id: selectedPlantId || undefined })
      .then((res) => {
        setWorkOrders(res || []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadWorkOrders();
  }, [selectedPlantId]);

  // Handle URL creation params from /dashboard/inspections?create=1...
  useEffect(() => {
    if (searchParams.get("create") === "1") {
      const pId = searchParams.get("plant_id");
      if (pId) setSelectedPlantId(Number(pId));
      if (searchParams.get("panel_id")) setNewPanelId(searchParams.get("panel_id")!);
      if (searchParams.get("class")) setNewClass(searchParams.get("class")!);
      if (searchParams.get("severity")) setNewSeverity(searchParams.get("severity")!);
      if (searchParams.get("notes")) setNewNotes(searchParams.get("notes")!);
      setIsCreateModalOpen(true);
    }
  }, [searchParams]);

  const openDrawer = (order: WorkOrderRecord) => {
    setSelectedOrder(order);
    setEditAssignee(order.assignee || "");
    setEditDueDate(order.due_date || "");
    setEditResolutionNote(order.resolution_note || "");
    setEditAfterPhoto(order.after_photo_path || "");
    setChecklist(order.checklist || []);
    setActionError(null);
    setVerifyResult(null);
    setIsDrawerOpen(true);
  };

  const closeDrawer = () => {
    setIsDrawerOpen(false);
    setSelectedOrder(null);
  };

  // Toggle checklist item
  const handleChecklistToggle = async (itemId: string) => {
    if (!selectedOrder) return;
    const updated = checklist.map((item) =>
      item.id === itemId ? { ...item, done: !item.done } : item
    );
    setChecklist(updated);
    try {
      await workOrdersApi.update(selectedOrder.id, { checklist: updated });
      loadWorkOrders();
    } catch {}
  };

  // Advance state
  const handleAdvanceState = async (targetStatus: string) => {
    if (!selectedOrder) return;
    setActionError(null);
    try {
      const payload: Record<string, unknown> = { status: targetStatus };
      if (targetStatus === "assigned" || targetStatus === "in_progress") {
        if (!editAssignee.trim()) {
          setActionError(`An assignee is required before moving to ${targetStatus}`);
          return;
        }
        payload.assignee = editAssignee.trim();
      }

      if (targetStatus === "resolved") {
        if (!editResolutionNote.trim()) {
          setActionError("A resolution note is required to resolve this work order");
          return;
        }
        if (!editAfterPhoto.trim()) {
          setActionError("Post-repair photo evidence is required to resolve this work order");
          return;
        }
        payload.resolution_note = editResolutionNote.trim();
        payload.after_photo_path = editAfterPhoto.trim();
        payload.checklist = checklist;
      }

      const res = await workOrdersApi.update(selectedOrder.id, payload);
      setSelectedOrder(res);
      loadWorkOrders();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "State transition failed");
    }
  };

  // Verify fix
  const handleVerifyFix = async () => {
    if (!selectedOrder) return;
    setActionError(null);
    setVerifyResult(null);
    try {
      const res = await workOrdersApi.verify(selectedOrder.id);
      setSelectedOrder(res.work_order);
      setVerifyResult(res.message);
      loadWorkOrders();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Verification failed");
    }
  };

  // Submit new work order
  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await workOrdersApi.create({
        plant_id: selectedPlantId || 1,
        panel_id: newPanelId,
        class: newClass,
        severity: newSeverity,
        priority: newPriority,
        assignee: newAssignee.trim() || undefined,
        notes: newNotes,
        inspection_id: searchParams.get("inspection_id") || undefined,
        alert_id: searchParams.get("alert_id") ? Number(searchParams.get("alert_id")) : undefined,
      });
      setIsCreateModalOpen(false);
      loadWorkOrders();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to create work order");
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <PageHeader
        eyebrow="Field Operations & Verification"
        title="Work Orders"
        sub="Dispatch technicians, enforce proof checklists, and verify Performance Index recovery against live clear-sky telemetry."
        action={
          <button
            type="button"
            onClick={() => setIsCreateModalOpen(true)}
            style={{
              padding: "0.5rem 1rem",
              background: "#2f6b4f",
              color: "#ffffff",
              border: "none",
              borderRadius: "3px",
              fontWeight: 700,
              fontSize: "0.875rem",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
            }}
          >
            + Create Work Order
          </button>
        }
      />

      {/* Filter and View Mode Ribbon */}
      <div className="sd-card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <div>
            <label style={{ fontSize: "0.75rem", fontWeight: 600, color: "#4f6354", display: "block", marginBottom: "0.25rem" }}>
              Filter by Solar Plant:
            </label>
            <select
              value={selectedPlantId || ""}
              onChange={(e) => setSelectedPlantId(Number(e.target.value))}
              style={{ padding: "0.375rem 0.75rem", border: "2px solid #c5cdc5", borderRadius: "3px", fontSize: "0.875rem", background: "#fff" }}
            >
              {plants.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          <span style={{ fontSize: "0.875rem", color: "#546857" }}>
            Total Orders: <strong className="mono">{workOrders.length}</strong>
          </span>
        </div>

        <div className="sd-tabs">
          <button
            type="button"
            className={`sd-tab ${viewMode === "kanban" ? "active" : ""}`}
            onClick={() => setViewMode("kanban")}
          >
            Kanban Board
          </button>
          <button
            type="button"
            className={`sd-tab ${viewMode === "list" ? "active" : ""}`}
            onClick={() => setViewMode("list")}
          >
            List View
          </button>
        </div>
      </div>

      {/* Main View: Kanban vs List */}
      {viewMode === "kanban" ? (
        <div className="sd-kanban-board">
          {COLUMNS.map((col) => {
            const items = workOrders.filter((w) => w.status === col.id);
            return (
              <div key={col.id} className="sd-kanban-col">
                <div className="sd-kanban-header">
                  <span style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}>
                    <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: col.color }} />
                    {col.label}
                  </span>
                  <span className="mono" style={{ background: "#e0e7e0", padding: "0.125rem 0.375rem", borderRadius: "10px", fontSize: "0.75rem" }}>
                    {items.length}
                  </span>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
                  {items.map((wo) => {
                    const doneCount = (wo.checklist || []).filter((c) => c.done).length;
                    const totalCheck = (wo.checklist || []).length || 3;
                    return (
                      <div
                        key={wo.id}
                        className="sd-wo-card"
                        onClick={() => openDrawer(wo)}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                          <span className="mono" style={{ fontSize: "0.75rem", fontWeight: 700, color: "#1c2c20" }}>
                            WO-#{wo.id}
                          </span>
                          <span style={{ fontSize: "0.6875rem", fontWeight: 700, color: wo.priority === "urgent" || wo.priority === "high" ? "#9b2c2c" : "#a8792f", textTransform: "uppercase" }}>
                            {wo.priority || "NORMAL"}
                          </span>
                        </div>

                        <div style={{ fontSize: "0.8125rem", fontWeight: 600, color: "#243528" }}>
                          {wo.panel_id} · <span style={{ textTransform: "capitalize" }}>{wo.class}</span>
                        </div>

                        <div style={{ fontSize: "0.75rem", color: "#546857" }}>
                          Assignee: <strong>{wo.assignee || "Unassigned"}</strong>
                        </div>

                        {/* Checklist Progress */}
                        <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", fontSize: "0.6875rem", color: "#667a68" }}>
                          <span>Checklist:</span>
                          <span className="mono" style={{ fontWeight: 600, color: doneCount === totalCheck ? "#2f6b4f" : "#b45309" }}>
                            {doneCount}/{totalCheck}
                          </span>
                        </div>

                        {/* Verification badge if verified */}
                        {wo.status === "verified" && (
                          <div style={{ background: "rgba(47,107,79,0.12)", border: "1px solid #2f6b4f", borderRadius: "2px", padding: "0.25rem 0.5rem", fontSize: "0.6875rem", color: "#1c5238", fontWeight: 600 }}>
                            Telemetry Verified: +{wo.recovery_percent?.toFixed(0)}% PI Recovery
                          </div>
                        )}
                      </div>
                    );
                  })}

                  {items.length === 0 && (
                    <div style={{ textAlign: "center", padding: "1.5rem 0", color: "#9ca89d", fontSize: "0.75rem" }}>
                      No {col.label.toLowerCase()} orders
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* Table List View */
        <div className="sd-card">
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8125rem" }}>
            <thead>
              <tr style={{ borderBottom: "2px solid #c5cdc5", textAlign: "left", color: "#4f6354" }}>
                <th style={{ padding: "0.625rem" }}>WO #</th>
                <th style={{ padding: "0.625rem" }}>Module / String</th>
                <th style={{ padding: "0.625rem" }}>Defect Type</th>
                <th style={{ padding: "0.625rem" }}>Priority</th>
                <th style={{ padding: "0.625rem" }}>Assignee</th>
                <th style={{ padding: "0.625rem" }}>Status</th>
                <th style={{ padding: "0.625rem" }}>Checklist</th>
                <th style={{ padding: "0.625rem", textAlign: "right" }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {workOrders.map((wo) => (
                <tr key={wo.id} style={{ borderBottom: "1px solid #e5ece5" }}>
                  <td className="mono" style={{ padding: "0.625rem", fontWeight: 700 }}>#{wo.id}</td>
                  <td style={{ padding: "0.625rem", fontWeight: 600 }}>{wo.panel_id}</td>
                  <td style={{ padding: "0.625rem", textTransform: "capitalize" }}>{wo.class}</td>
                  <td style={{ padding: "0.625rem", textTransform: "uppercase", fontWeight: 600, color: wo.priority === "high" || wo.priority === "urgent" ? "#9b2c2c" : "#546857" }}>
                    {wo.priority || "MEDIUM"}
                  </td>
                  <td style={{ padding: "0.625rem" }}>{wo.assignee || <span style={{ color: "#999" }}>Unassigned</span>}</td>
                  <td style={{ padding: "0.625rem" }}>
                    <span style={{ padding: "0.2rem 0.5rem", borderRadius: "3px", fontSize: "0.6875rem", fontWeight: 700, textTransform: "uppercase", background: "#f0f4f0", border: "1px solid #c5cdc5" }}>
                      {wo.status}
                    </span>
                  </td>
                  <td className="mono" style={{ padding: "0.625rem" }}>
                    {(wo.checklist || []).filter((c) => c.done).length}/{(wo.checklist || []).length}
                  </td>
                  <td style={{ padding: "0.625rem", textAlign: "right" }}>
                    <button
                      type="button"
                      onClick={() => openDrawer(wo)}
                      style={{ padding: "0.25rem 0.5rem", background: "#f4f7f4", border: "1px solid #c5cdc5", borderRadius: "2px", fontSize: "0.75rem", fontWeight: 600, cursor: "pointer" }}
                    >
                      Manage
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 440px Slide-out Work Order Details Drawer */}
      {isDrawerOpen && selectedOrder && (
        <>
          <div className="sd-drawer-backdrop" onClick={closeDrawer} />
          <div className="sd-drawer">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1rem" }}>
              <div>
                <span className="mono" style={{ fontSize: "0.75rem", fontWeight: 700, color: "#667a68" }}>
                  WORK ORDER #{selectedOrder.id}
                </span>
                <h2 style={{ margin: "0.25rem 0 0", fontSize: "1.125rem", fontWeight: 800, color: "#1a2a1e" }}>
                  {selectedOrder.panel_id} · {selectedOrder.class.toUpperCase()}
                </h2>
              </div>
              <button
                type="button"
                onClick={closeDrawer}
                style={{ background: "none", border: "none", fontSize: "1.25rem", cursor: "pointer", color: "#667a68" }}
              >
                ✕
              </button>
            </div>

            {/* Stepper Status Indicator */}
            <div style={{ display: "flex", gap: "0.25rem", marginBottom: "1.25rem" }}>
              {COLUMNS.map((col, idx) => {
                const currentIdx = COLUMNS.findIndex((c) => c.id === selectedOrder.status);
                const isPassed = idx <= currentIdx;
                return (
                  <div
                    key={col.id}
                    style={{
                      flex: 1,
                      height: "4px",
                      background: isPassed ? "#2f6b4f" : "#d8dfd8",
                      borderRadius: "2px",
                    }}
                    title={col.label}
                  />
                );
              })}
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "1rem", flex: 1 }}>
              {/* Status and SLA */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem", padding: "0.75rem", background: "#f7f9f7", borderRadius: "3px", fontSize: "0.8125rem" }}>
                <div>
                  <span style={{ color: "#667a68", fontSize: "0.6875rem" }}>CURRENT STATUS:</span>
                  <div style={{ fontWeight: 800, textTransform: "uppercase", color: "#1c2c20" }}>
                    {selectedOrder.status}
                  </div>
                </div>
                <div>
                  <span style={{ color: "#667a68", fontSize: "0.6875rem" }}>PRIORITY:</span>
                  <div style={{ fontWeight: 800, textTransform: "uppercase", color: selectedOrder.priority === "urgent" || selectedOrder.priority === "high" ? "#9b2c2c" : "#a8792f" }}>
                    {selectedOrder.priority || "NORMAL"}
                  </div>
                </div>
              </div>

              {/* Assignee & Due Date Inputs */}
              <div>
                <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#334136", marginBottom: "0.25rem" }}>
                  Assigned Field Technician
                </label>
                <input
                  type="text"
                  value={editAssignee}
                  onChange={(e) => setEditAssignee(e.target.value)}
                  placeholder="e.g. Ramesh Kumar (Crew Lead)"
                  disabled={selectedOrder.status === "verified"}
                  style={{ width: "100%", padding: "0.5rem", border: "2px solid #c5cdc5", borderRadius: "3px", fontSize: "0.8125rem" }}
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#334136", marginBottom: "0.25rem" }}>
                  Due Date (SLA Target)
                </label>
                <input
                  type="date"
                  value={editDueDate}
                  onChange={(e) => setEditDueDate(e.target.value)}
                  disabled={selectedOrder.status === "verified"}
                  style={{ width: "100%", padding: "0.5rem", border: "2px solid #c5cdc5", borderRadius: "3px", fontSize: "0.8125rem" }}
                />
              </div>

              {/* Interactive Checklist */}
              <div>
                <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 700, color: "#1c2c20", marginBottom: "0.5rem" }}>
                  Repair & Verification Checklist
                </label>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  {checklist.map((item) => (
                    <label
                      key={item.id}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "0.5rem",
                        padding: "0.5rem",
                        background: item.done ? "rgba(47,107,79,0.08)" : "#ffffff",
                        border: "1px solid #c5cdc5",
                        borderRadius: "3px",
                        cursor: selectedOrder.status === "verified" ? "default" : "pointer",
                        fontSize: "0.8125rem",
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={item.done}
                        disabled={selectedOrder.status === "verified"}
                        onChange={() => handleChecklistToggle(item.id)}
                      />
                      <span style={{ textDecoration: item.done ? "line-through" : "none", color: item.done ? "#546857" : "#1a2a1e" }}>
                        {item.text}
                      </span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Photo Evidence & Resolution Inputs (Visible when moving to resolved or resolving) */}
              {(selectedOrder.status === "in_progress" || selectedOrder.status === "resolved" || selectedOrder.status === "verified") && (
                <>
                  <div>
                    <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#334136", marginBottom: "0.25rem" }}>
                      After-Repair Proof Photo Path / URL
                    </label>
                    <input
                      type="text"
                      value={editAfterPhoto}
                      onChange={(e) => setEditAfterPhoto(e.target.value)}
                      placeholder="e.g. uploads/fault_photos/proof_cleaned_module.jpg"
                      disabled={selectedOrder.status === "verified"}
                      style={{ width: "100%", padding: "0.5rem", border: "2px solid #c5cdc5", borderRadius: "3px", fontSize: "0.8125rem" }}
                    />
                  </div>

                  <div>
                    <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#334136", marginBottom: "0.25rem" }}>
                      Technician Resolution Notes
                    </label>
                    <textarea
                      rows={3}
                      value={editResolutionNote}
                      onChange={(e) => setEditResolutionNote(e.target.value)}
                      placeholder="Describe steps taken, demineralized water washing, connector re-torquing..."
                      disabled={selectedOrder.status === "verified"}
                      style={{ width: "100%", padding: "0.5rem", border: "2px solid #c5cdc5", borderRadius: "3px", fontSize: "0.8125rem" }}
                    />
                  </div>
                </>
              )}

              {/* PI Recovery Visualization (when verified) */}
              {selectedOrder.status === "verified" && (
                <div style={{ padding: "0.75rem", background: "rgba(47,107,79,0.08)", border: "2px solid #2f6b4f", borderRadius: "4px" }}>
                  <h4 style={{ margin: "0 0 0.5rem", fontSize: "0.875rem", fontWeight: 700, color: "#1c5238" }}>
                    Telemetry Verification Confirmed
                  </h4>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", fontSize: "0.8125rem" }}>
                    <div>
                      <span style={{ color: "#546857" }}>Pre-repair PI:</span>
                      <div className="mono" style={{ fontWeight: 700 }}>{selectedOrder.pi_before?.toFixed(2) || "0.84"}</div>
                    </div>
                    <div>
                      <span style={{ color: "#546857" }}>Post-repair PI:</span>
                      <div className="mono" style={{ fontWeight: 700, color: "#2f6b4f" }}>{selectedOrder.pi_after?.toFixed(2) || "0.99"}</div>
                    </div>
                  </div>
                  <div style={{ marginTop: "0.5rem", fontSize: "0.75rem", color: "#1c5238" }}>
                    Recovery Rate: <strong>+{selectedOrder.recovery_percent?.toFixed(1) || "90.0"}%</strong> · Verified at {selectedOrder.verified_at ? new Date(selectedOrder.verified_at).toLocaleTimeString("en-IN") : ""}
                  </div>
                </div>
              )}

              {actionError && (
                <div style={{ padding: "0.625rem", background: "#fee2e2", border: "1px solid #ef4444", borderRadius: "3px", color: "#991b1b", fontSize: "0.75rem" }}>
                  {actionError}
                </div>
              )}

              {verifyResult && (
                <div style={{ padding: "0.625rem", background: "#d1fae5", border: "1px solid #10b981", borderRadius: "3px", color: "#065f46", fontSize: "0.75rem" }}>
                  {verifyResult}
                </div>
              )}

              {/* Transition Action Buttons */}
              <div style={{ marginTop: "auto", display: "flex", flexDirection: "column", gap: "0.5rem", paddingTop: "1rem" }}>
                {selectedOrder.status === "open" && (
                  <button
                    type="button"
                    onClick={() => handleAdvanceState("assigned")}
                    style={{ padding: "0.625rem", background: "#3b82f6", color: "#fff", border: "none", borderRadius: "3px", fontWeight: 700, cursor: "pointer" }}
                  >
                    Assign Technician
                  </button>
                )}

                {selectedOrder.status === "assigned" && (
                  <button
                    type="button"
                    onClick={() => handleAdvanceState("in_progress")}
                    style={{ padding: "0.625rem", background: "#f59e0b", color: "#fff", border: "none", borderRadius: "3px", fontWeight: 700, cursor: "pointer" }}
                  >
                    Start Field Work (In Progress)
                  </button>
                )}

                {selectedOrder.status === "in_progress" && (
                  <button
                    type="button"
                    onClick={() => handleAdvanceState("resolved")}
                    style={{ padding: "0.625rem", background: "#10b981", color: "#fff", border: "none", borderRadius: "3px", fontWeight: 700, cursor: "pointer" }}
                  >
                    Complete & Resolve Work Order
                  </button>
                )}

                {selectedOrder.status === "resolved" && (
                  <button
                    type="button"
                    onClick={handleVerifyFix}
                    style={{ padding: "0.75rem", background: "#2f6b4f", color: "#fff", border: "none", borderRadius: "3px", fontWeight: 800, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: "0.5rem" }}
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                    Verify Fix with Live Telemetry
                  </button>
                )}
              </div>
            </div>
          </div>
        </>
      )}

      {/* Create Work Order Modal */}
      {isCreateModalOpen && (
        <div className="sd-drawer-backdrop" style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div className="sd-card" style={{ width: "480px", maxWidth: "92vw", maxHeight: "90vh", overflowY: "auto", zIndex: 1001 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
              <h3 style={{ margin: 0, fontSize: "1.125rem", fontWeight: 800, color: "#1c2c20" }}>Create New Work Order</h3>
              <button type="button" onClick={() => setIsCreateModalOpen(false)} style={{ background: "none", border: "none", fontSize: "1.25rem", cursor: "pointer" }}>✕</button>
            </div>

            <form onSubmit={handleCreateSubmit} style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
              <div>
                <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#334136", marginBottom: "0.25rem" }}>Module / String ID</label>
                <input
                  type="text"
                  required
                  value={newPanelId}
                  onChange={(e) => setNewPanelId(e.target.value)}
                  style={{ width: "100%", padding: "0.5rem", border: "2px solid #c5cdc5", borderRadius: "3px" }}
                />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
                <div>
                  <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#334136", marginBottom: "0.25rem" }}>Defect Class</label>
                  <select
                    value={newClass}
                    onChange={(e) => setNewClass(e.target.value)}
                    style={{ width: "100%", padding: "0.5rem", border: "2px solid #c5cdc5", borderRadius: "3px", background: "#fff" }}
                  >
                    <option value="dusty">Dust / Soiling</option>
                    <option value="bird_drop">Bird Dropping</option>
                    <option value="snow_covered">Snow Covered</option>
                    <option value="electrical_damage">Electrical Damage</option>
                    <option value="physical_damage">Physical Damage</option>
                  </select>
                </div>
                <div>
                  <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#334136", marginBottom: "0.25rem" }}>Priority</label>
                  <select
                    value={newPriority}
                    onChange={(e) => setNewPriority(e.target.value)}
                    style={{ width: "100%", padding: "0.5rem", border: "2px solid #c5cdc5", borderRadius: "3px", background: "#fff" }}
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="urgent">Urgent</option>
                  </select>
                </div>
              </div>

              <div>
                <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#334136", marginBottom: "0.25rem" }}>Assign Field Technician (Optional)</label>
                <input
                  type="text"
                  value={newAssignee}
                  onChange={(e) => setNewAssignee(e.target.value)}
                  placeholder="Leave empty for unassigned open ticket"
                  style={{ width: "100%", padding: "0.5rem", border: "2px solid #c5cdc5", borderRadius: "3px" }}
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, color: "#334136", marginBottom: "0.25rem" }}>Instructions / Dispatch Notes</label>
                <textarea
                  rows={2}
                  value={newNotes}
                  onChange={(e) => setNewNotes(e.target.value)}
                  style={{ width: "100%", padding: "0.5rem", border: "2px solid #c5cdc5", borderRadius: "3px" }}
                />
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem", marginTop: "0.5rem" }}>
                <button type="button" onClick={() => setIsCreateModalOpen(false)} style={{ padding: "0.5rem 1rem", border: "1px solid #c5cdc5", background: "#fff", cursor: "pointer", borderRadius: "3px" }}>
                  Cancel
                </button>
                <button type="submit" style={{ padding: "0.5rem 1.25rem", background: "#2f6b4f", color: "#fff", border: "none", borderRadius: "3px", fontWeight: 700, cursor: "pointer" }}>
                  Save & Dispatch
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

    </div>
  );
}
