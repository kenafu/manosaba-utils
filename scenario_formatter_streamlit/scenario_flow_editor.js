import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { 
  Save, 
  Plus, 
  Trash2, 
  Search, 
  Download, 
  Database,
  ArrowRight,
  Filter,
  Image as ImageIcon,
  Music,
  Volume2,
  GitBranch,
  Tag,
  FileText,
  Upload,
  Link as LinkIcon,
  Copy
} from 'lucide-react';

/**
 * Scenario Flow Manager
 * Manages scenario_text (Source) and scenario_flow (Relations) tables.
 */

// ------------------------------------------------------------------
// Types & Constants
// ------------------------------------------------------------------
const ROW_HEIGHT = 45;
const HEADER_HEIGHT = 40;
const OVERSCAN_COUNT = 10;

// カラム定義
// scenario_text (Source) fields are mainly read-only reference
// scenario_flow fields are editable
const COLUMNS = [
  // --- Scenario Text Info (Source) ---
  { id: 'uid', label: 'UID (From)', width: 180, frozen: true, readOnly: true, group: 'Text Source' },
  { id: 'actor', label: 'Actor', width: 100, readOnly: true, group: 'Text Source' },
  { id: 'text', label: 'Text Preview', width: 300, readOnly: true, group: 'Text Source' },
  
  // --- Scenario Flow Info (Editable) ---
  { id: 'transition_type', label: 'Type', width: 100, type: 'select', options: ['NEXT', 'SELECT', 'JUMP', 'END'], group: 'Flow Setting', editable: true },
  { id: 'to_uid', label: 'Target UID (To)', width: 180, icon: ArrowRight, group: 'Flow Setting', editable: true, placeholder: '遷移先のUID' },
  { id: 'selection_label', label: 'Selection Label', width: 150, group: 'Flow Setting', editable: true, placeholder: '選択肢の文言' },
  { id: 'condition_script', label: 'Condition', width: 150, icon: GitBranch, group: 'Flow Setting', editable: true, placeholder: '条件式' },
  { id: 'on_enter_action', label: 'Action', width: 150, group: 'Flow Setting', editable: true, placeholder: '実行アクション' },
  { id: 'disp_order', label: 'Order', width: 60, type: 'number', group: 'Flow Setting', editable: true },
];

const TOTAL_WIDTH = COLUMNS.reduce((acc, col) => acc + col.width, 0) + 60;

// ------------------------------------------------------------------
// Helper: CSV Parser
// ------------------------------------------------------------------
const parseCSV = (text) => {
  const lines = text.split(/\r\n|\n/);
  const headers = lines[0].split(',').map(h => h.trim());
  
  const result = [];
  for (let i = 1; i < lines.length; i++) {
    if (!lines[i].trim()) continue;
    
    // Simple CSV parse handling quotes (Not robust for all cases but sufficient for sample)
    const row = {};
    let currentLine = lines[i];
    let inQuote = false;
    let fieldStart = 0;
    let colIndex = 0;
    
    // Very naive split considering quotes
    const fields = [];
    let field = '';
    for (let charIdx = 0; charIdx < currentLine.length; charIdx++) {
      const char = currentLine[charIdx];
      if (char === '"') {
        inQuote = !inQuote;
      } else if (char === ',' && !inQuote) {
        fields.push(field);
        field = '';
      } else {
        field += char;
      }
    }
    fields.push(field); // Last field

    headers.forEach((header, index) => {
      let val = fields[index] || '';
      // Remove surrounding quotes
      if (val.startsWith('"') && val.endsWith('"')) {
        val = val.slice(1, -1);
      }
      row[header] = val;
    });
    result.push(row);
  }
  return result;
};

// ------------------------------------------------------------------
// Helper: Generate SQL
// ------------------------------------------------------------------
const generateSQL = (flows) => {
  let sql = 'INSERT INTO scenario_flow (from_uid, to_uid, transition_type, selection_label, condition_script, disp_order, on_enter_action) VALUES\n';
  const values = flows.map(f => {
    return `('${f.from_uid}', '${f.to_uid}', '${f.transition_type || 'NEXT'}', '${f.selection_label || ''}', '${f.condition_script || ''}', ${f.disp_order || 0}, '${f.on_enter_action || ''}')`;
  });
  return sql + values.join(',\n') + ';';
};

export default function ScenarioFlowEditor() {
  // ------------------------------------------------------------------
  // State
  // ------------------------------------------------------------------
  // scenario_text table data (Source)
  const [textData, setTextData] = useState([]);
  // scenario_flow table data (Editable relations)
  const [flowData, setFlowData] = useState([]);
  
  // View State
  const [scrollTop, setScrollTop] = useState(0);
  const [containerHeight, setContainerHeight] = useState(0);
  const [selectedCell, setSelectedCell] = useState({ rowIndex: null, colId: null });
  const [editingCell, setEditingCell] = useState(null);
  const [statusMsg, setStatusMsg] = useState('Waiting for CSV import...');

  const containerRef = useRef(null);
  const editInputRef = useRef(null);
  const fileInputRef = useRef(null);

  // ------------------------------------------------------------------
  // Computed Data for View (Join Text & Flow)
  // ------------------------------------------------------------------
  // We need to flatten the 1:N relationship (One text -> Many flows) for the table view
  const viewRows = useMemo(() => {
    if (textData.length === 0) return [];

    const rows = [];
    
    // Map flows by from_uid for faster lookup
    const flowMap = new Map();
    flowData.forEach(flow => {
      if (!flowMap.has(flow.from_uid)) {
        flowMap.set(flow.from_uid, []);
      }
      flowMap.get(flow.from_uid).push(flow);
    });

    textData.forEach((textRow, textIndex) => {
      const relatedFlows = flowMap.get(textRow.uid);
      
      if (relatedFlows && relatedFlows.length > 0) {
        // Create a row for each flow (branch)
        relatedFlows.forEach((flow, flowIndex) => {
          rows.push({
            _key: `${textRow.uid}_${flowIndex}`, // Unique key for view
            _sourceIndex: textIndex,
            _flowIndex: flowData.indexOf(flow), // Reference to original flow data
            ...textRow, // Spread text data (uid, actor, text...)
            ...flow,    // Spread flow data (transition_type, to_uid...)
            isBranch: relatedFlows.length > 1,
            branchIndex: flowIndex
          });
        });
      } else {
        // No flow defined yet: Show 1 row with empty flow fields
        rows.push({
          _key: `${textRow.uid}_empty`,
          _sourceIndex: textIndex,
          _flowIndex: -1, // New flow needs to be created
          ...textRow,
          transition_type: 'NEXT', // Default
          to_uid: '',
          selection_label: '',
          condition_script: '',
          disp_order: 0,
          on_enter_action: '',
          isBranch: false
        });
      }
    });
    return rows;
  }, [textData, flowData]);

  // ------------------------------------------------------------------
  // Virtual Scroll Calculations
  // ------------------------------------------------------------------
  const totalContentHeight = viewRows.length * ROW_HEIGHT + HEADER_HEIGHT;
  
  const visibleRange = useMemo(() => {
    const effectiveScrollTop = Math.max(0, scrollTop - HEADER_HEIGHT);
    const startIndex = Math.max(0, Math.floor(effectiveScrollTop / ROW_HEIGHT) - OVERSCAN_COUNT);
    const endIndex = Math.min(
      viewRows.length, 
      Math.ceil((effectiveScrollTop + containerHeight) / ROW_HEIGHT) + OVERSCAN_COUNT
    );
    return { startIndex, endIndex };
  }, [scrollTop, containerHeight, viewRows.length]);

  const visibleRows = useMemo(() => {
    return viewRows.slice(visibleRange.startIndex, visibleRange.endIndex).map((row, i) => ({
      ...row,
      _viewIndex: visibleRange.startIndex + i
    }));
  }, [viewRows, visibleRange]);

  // ------------------------------------------------------------------
  // Handlers
  // ------------------------------------------------------------------
  
  // Import CSV
  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (evt) => {
      try {
        const parsed = parseCSV(evt.target.result);
        if (parsed.length > 0) {
          setTextData(parsed);
          // Initialize empty flow data or try to link default 'NEXT'
          setFlowData([]); 
          setStatusMsg(`Imported ${parsed.length} scenarios. Please configure flows.`);
        }
      } catch (err) {
        alert('Failed to parse CSV');
        console.error(err);
      }
    };
    reader.readAsText(file);
  };

  // Auto-Link Logic (Simple Sequence)
  const autoLinkFlows = () => {
    if (!window.confirm('現在のフロー設定をクリアし、上から順に「NEXT」で自動的に紐付けますか？')) return;
    
    const newFlows = [];
    for (let i = 0; i < textData.length - 1; i++) {
      newFlows.push({
        from_uid: textData[i].uid,
        to_uid: textData[i + 1].uid,
        transition_type: 'NEXT',
        disp_order: 0
      });
    }
    setFlowData(newFlows);
    setStatusMsg('Auto-linked flows sequentially.');
  };

  // Add Branch (Duplicate Row for same Source)
  const addBranch = (sourceUid) => {
    const newFlow = {
      from_uid: sourceUid,
      to_uid: '',
      transition_type: 'SELECT',
      selection_label: 'New Choice',
      disp_order: 0
    };
    setFlowData(prev => [...prev, newFlow]);
  };

  // Delete Flow
  const deleteFlow = (flowIndex) => {
    if (flowIndex === -1) return; // Can't delete the placeholder
    setFlowData(prev => prev.filter((_, i) => i !== flowIndex));
  };

  // Cell Editing
  const startEditing = (rowIndex, colId, initialValue, rowData) => {
    const colDef = COLUMNS.find(c => c.id === colId);
    if (!colDef.editable) return;
    
    setEditingCell({ 
      rowIndex, 
      colId, 
      value: initialValue,
      originalRow: rowData
    });
  };

  const commitEditing = () => {
    if (!editingCell) return;
    
    const { rowIndex, colId, value, originalRow } = editingCell;
    const flowIndex = originalRow._flowIndex;

    if (flowIndex === -1) {
      // Create NEW flow entry
      const newFlow = {
        from_uid: originalRow.uid,
        to_uid: '',
        transition_type: 'NEXT',
        disp_order: 0,
        [colId]: value
      };
      setFlowData(prev => [...prev, newFlow]);
    } else {
      // Update EXISTING flow entry
      setFlowData(prev => prev.map((flow, i) => 
        i === flowIndex ? { ...flow, [colId]: value } : flow
      ));
    }
    
    setEditingCell(null);
    if (containerRef.current) containerRef.current.focus();
  };

  const handleKeyDown = (e) => {
    if (editingCell) {
      if (e.key === 'Enter') {
        commitEditing();
      } else if (e.key === 'Escape') {
        setEditingCell(null);
      }
      return;
    }
    // Navigation logic could be added here similar to previous version
  };

  const exportSQL = () => {
    const sql = generateSQL(flowData);
    const blob = new Blob([sql], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'scenario_flow.sql';
    a.click();
  };

  // Resize Observer
  useEffect(() => {
    const observer = new ResizeObserver(entries => {
      for (let entry of entries) setContainerHeight(entry.contentRect.height);
    });
    if (containerRef.current) observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (editingCell && editInputRef.current) editInputRef.current.focus();
  }, [editingCell]);

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------
  return (
    <div className="flex flex-col h-screen w-screen bg-gray-900 text-gray-100 font-sans overflow-hidden">
      
      {/* Header Toolbar */}
      <div className="flex items-center justify-between px-4 py-3 bg-gray-800 border-b border-gray-700 shadow-lg z-30">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2 text-blue-400 font-bold text-lg">
            <GitBranch className="w-6 h-6" />
            <span>Scenario Flow Editor</span>
          </div>
          
          <div className="flex items-center gap-2">
             <input 
               type="file" 
               accept=".csv,.txt" 
               ref={fileInputRef} 
               onChange={handleFileUpload} 
               className="hidden" 
             />
             <button 
               onClick={() => fileInputRef.current.click()}
               className="flex items-center gap-2 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-xs text-gray-200 border border-gray-600 transition-colors"
             >
               <Upload className="w-3 h-3" />
               Import CSV (Text)
             </button>

             <button 
               onClick={autoLinkFlows}
               className="flex items-center gap-2 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-xs text-gray-200 border border-gray-600 transition-colors"
               disabled={textData.length === 0}
             >
               <LinkIcon className="w-3 h-3" />
               Auto Link (Sequential)
             </button>
          </div>
        </div>

        <div className="flex items-center gap-4">
           <span className="text-xs text-gray-400">{statusMsg}</span>
           <button 
             onClick={exportSQL}
             className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded shadow text-sm font-medium transition-transform active:scale-95"
             disabled={flowData.length === 0}
           >
             <Download className="w-4 h-4" />
             Export SQL
           </button>
        </div>
      </div>

      {/* Main Grid */}
      <div 
        ref={containerRef}
        className="flex-1 overflow-auto bg-gray-950 relative outline-none"
        onScroll={e => setScrollTop(e.target.scrollTop)}
        onKeyDown={handleKeyDown}
        tabIndex={0}
      >
        <div style={{ height: totalContentHeight, minWidth: TOTAL_WIDTH, position: 'relative' }}>
          
          {/* Sticky Header */}
          <div 
            className="sticky top-0 z-20 flex bg-gray-900 border-b border-gray-700 text-xs font-bold text-gray-400 shadow-md"
            style={{ height: HEADER_HEIGHT, width: TOTAL_WIDTH }}
          >
            <div className="w-[60px] flex-shrink-0 flex items-center justify-center border-r border-gray-700 bg-gray-900">
              #
            </div>
            {COLUMNS.map(col => (
              <div 
                key={col.id} 
                className={`
                  flex items-center px-2 border-r border-gray-700 
                  ${col.group === 'Flow Setting' ? 'bg-gray-800 text-blue-300' : 'bg-gray-900'}
                `}
                style={{ width: col.width }}
              >
                {col.icon && <col.icon className="w-3 h-3 mr-1.5 opacity-70" />}
                <div className="flex flex-col">
                  <span className="opacity-50 text-[10px] uppercase">{col.group}</span>
                  <span>{col.label}</span>
                </div>
              </div>
            ))}
            {/* Actions Column Header */}
            <div className="flex-1 bg-gray-900 border-gray-700 px-2 flex items-center">Actions</div>
          </div>

          {/* Virtualized Rows */}
          {visibleRows.map((row) => (
            <div
              key={row._key}
              className={`
                absolute left-0 flex border-b border-gray-800 transition-colors group
                ${row.isBranch ? 'bg-blue-900/10' : ''}
                ${selectedCell.rowIndex === row._viewIndex ? 'bg-white/5' : 'hover:bg-white/5'}
              `}
              style={{ 
                height: ROW_HEIGHT, 
                width: TOTAL_WIDTH,
                top: row._viewIndex * ROW_HEIGHT + HEADER_HEIGHT, 
              }}
            >
              {/* Index / Branch Indicator */}
              <div className="w-[60px] flex-shrink-0 flex items-center justify-center text-xs text-gray-500 border-r border-gray-800 select-none bg-gray-900/50">
                 {row.isBranch ? (
                   <div className="flex flex-col items-center">
                     <GitBranch className="w-3 h-3 text-blue-400" />
                     <span className="text-[9px]">{row.branchIndex + 1}</span>
                   </div>
                 ) : (
                   row._sourceIndex + 1
                 )}
              </div>

              {/* Cells */}
              {COLUMNS.map((col) => {
                const isSelected = selectedCell.rowIndex === row._viewIndex && selectedCell.colId === col.id;
                const isEditing = editingCell?.rowIndex === row._viewIndex && editingCell?.colId === col.id;
                const cellValue = row[col.id];
                
                return (
                  <div
                    key={col.id}
                    onClick={() => {
                        setSelectedCell({ rowIndex: row._viewIndex, colId: col.id });
                        // If it's a Target UID column, maybe we can simplify selection?
                    }}
                    onDoubleClick={() => startEditing(row._viewIndex, col.id, cellValue, row)}
                    className={`
                      relative px-2 flex items-center text-sm border-r border-gray-800 cursor-default overflow-hidden
                      ${isSelected ? 'ring-1 ring-inset ring-blue-500 z-10' : ''}
                      ${col.readOnly ? 'text-gray-500' : 'text-gray-200'}
                      ${col.group === 'Flow Setting' ? 'bg-gray-800/20' : ''}
                    `}
                    style={{ width: col.width }}
                  >
                    {isEditing ? (
                      col.type === 'select' ? (
                        <select
                          ref={editInputRef}
                          className="w-full bg-gray-800 text-white outline-none border border-blue-500"
                          value={editingCell.value}
                          onChange={(e) => setEditingCell(prev => ({ ...prev, value: e.target.value }))}
                          onBlur={commitEditing}
                          onKeyDown={(e) => e.key === 'Enter' && commitEditing()}
                        >
                           {col.options.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                        </select>
                      ) : (
                        <input
                          ref={editInputRef}
                          type={col.type || "text"}
                          className="w-full h-full bg-gray-800 text-white outline-none px-1"
                          value={editingCell.value || ''}
                          onChange={(e) => setEditingCell(prev => ({ ...prev, value: e.target.value }))}
                          onBlur={commitEditing}
                        />
                      )
                    ) : (
                      <div className="truncate w-full" title={String(cellValue || '')}>
                        {cellValue || <span className="text-gray-700 italic text-xs">{col.placeholder}</span>}
                      </div>
                    )}
                  </div>
                );
              })}

              {/* Row Actions */}
              <div className="flex items-center px-2 gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                 <button 
                   onClick={() => addBranch(row.uid)}
                   title="Add Branch (Selection)"
                   className="p-1 hover:bg-blue-600 rounded text-gray-400 hover:text-white"
                 >
                   <GitBranch className="w-4 h-4" />
                 </button>
                 {row._flowIndex !== -1 && (
                   <button 
                     onClick={() => deleteFlow(row._flowIndex)}
                     title="Remove Flow"
                     className="p-1 hover:bg-red-600 rounded text-gray-400 hover:text-white"
                   >
                     <Trash2 className="w-4 h-4" />
                   </button>
                 )}
              </div>

            </div>
          ))}
          
          {textData.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center text-gray-500 flex-col gap-4">
              <Database className="w-12 h-12 opacity-20" />
              <p>Import "scenario_text" CSV to start editing flows.</p>
              <button 
                onClick={() => fileInputRef.current.click()}
                className="px-4 py-2 bg-blue-900/50 hover:bg-blue-800 text-blue-200 rounded border border-blue-800"
              >
                Select CSV File
              </button>
            </div>
          )}

        </div>
      </div>
      
      {/* Footer / Hint */}
      <div className="bg-gray-800 border-t border-gray-700 px-4 py-1 flex items-center justify-between text-xs text-gray-500">
         <div>Target Table: <strong>scenario_flow</strong></div>
         <div className="flex gap-4">
           <span>Double-click cells to edit</span>
           <span>Use 'Auto Link' for initial setup</span>
         </div>
      </div>
    </div>
  );
}