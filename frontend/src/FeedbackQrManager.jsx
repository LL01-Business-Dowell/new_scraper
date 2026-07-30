import React, { useState, useEffect } from 'react';
import { Building2, QrCode, Plus, RefreshCw, CheckCircle2, AlertCircle, Link as LinkIcon, UserPlus, Download, FileText } from 'lucide-react';
import QRCode from 'qrcode';
import axios from 'axios';
import { jsPDF } from 'jspdf';

export default function FeedbackQrManager() {
  const [clients, setClients] = useState([]);
  const [selectedClient, setSelectedClient] = useState('');
  const [qrList, setQrList] = useState([]);
  
  // Loading & Toggle Flags
  const [loadingClients, setLoadingClients] = useState(true);
  const [loadingQrs, setLoadingQrs] = useState(false);
  const [creating, setCreating] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [generatingPdf, setGeneratingPdf] = useState(false);
  
  // Add Client State
  const [showAddClient, setShowAddClient] = useState(false);
  const [newClientName, setNewClientName] = useState('');
  const [addingClient, setAddingClient] = useState(false);

  // Messages
  const [errorMsg, setErrorMsg] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  // Form Fields for QR Creation
  const [formData, setFormData] = useState({
    name: '',
    room_number: '',
    user_id: ''
  });

  const [activeQrImage, setActiveQrImage] = useState(null);

  // Auto-dismiss success notifications
  useEffect(() => {
    if (successMsg) {
      const timer = setTimeout(() => setSuccessMsg(''), 4000);
      return () => clearTimeout(timer);
    }
  }, [successMsg]);

  // Auto-dismiss error notifications
  useEffect(() => {
    if (errorMsg) {
      const timer = setTimeout(() => setErrorMsg(''), 5000);
      return () => clearTimeout(timer);
    }
  }, [errorMsg]);

  // 1. Fetch Client List on Load
  useEffect(() => {
    fetchClients();
  }, []);

  // 2. Fetch QRs when Selected Client changes
  useEffect(() => {
    if (selectedClient) {
      fetchClientQrs(selectedClient);
    } else {
      setQrList([]);
    }
  }, [selectedClient]);

  const fetchClients = async (selectClientName = null) => {
    setLoadingClients(true);
    try {
      const res = await axios.get('/api/feedback-qr/clients');
      const list = res.data.clients || [];
      setClients(list);

      if (selectClientName) {
        setSelectedClient(selectClientName);
      } else if (list.length > 0 && !selectedClient) {
        setSelectedClient(list[0]);
      }
    } catch (err) {
      setErrorMsg('Failed to load clients list from DataCube.');
    } finally {
      setLoadingClients(false);
    }
  };

  const fetchClientQrs = async (clientName) => {
    setLoadingQrs(true);
    setErrorMsg('');
    try {
      const res = await axios.get(`/api/feedback-qr/qrs/${clientName}`);
      const rawQrs = res.data.qr_codes || [];

      // Generate high-res QR Code image data URLs for display & export
      const processedQrs = await Promise.all(
        rawQrs.map(async (item) => {
          const qrDataUrl = await QRCode.toDataURL(item.target_url || `https://reviewanalysis.uxlivinglab.org/feedback?id=${item.sequence_number || item.full_id}`, { width: 300, margin: 1 });
          return { ...item, qrDataUrl };
        })
      );

      setQrList(processedQrs);
    } catch (err) {
      setErrorMsg(`Failed to fetch QR codes for client: ${clientName}`);
    } finally {
      setLoadingQrs(false);
    }
  };

  const handleAddClient = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setSuccessMsg('');

    if (!newClientName.trim()) {
      setErrorMsg('Please enter a client name.');
      return;
    }

    setAddingClient(true);
    try {
      const res = await axios.post('/api/feedback-qr/add-client', {
        client_name: newClientName
      });

      const createdClient = res.data.client_name;
      setSuccessMsg(`Client '${createdClient}' created successfully!`);
      setNewClientName('');
      setShowAddClient(false);

      await fetchClients(createdClient);
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || 'Failed to add new client.');
    } finally {
      setAddingClient(false);
    }
  };

  const handleInputChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleCreateQr = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    setSuccessMsg('');

    if (!formData.name || !formData.room_number || !formData.user_id) {
      setErrorMsg('Please fill in all fields (Name, Room Number, ID).');
      return;
    }

    setCreating(true);

    try {
      const payload = {
        client_name: selectedClient,
        name: formData.name,
        room_number: formData.room_number,
        user_id: formData.user_id
      };

      const res = await axios.post('/api/feedback-qr/create', payload);
      const newRecord = res.data.record;

      const qrDataUrl = await QRCode.toDataURL(newRecord.target_url, { width: 300, margin: 1 });
      const fullRecord = { ...newRecord, qrDataUrl };

      setQrList((prev) => [fullRecord, ...prev]);

      setFormData({ name: '', room_number: '', user_id: '' });
      setSuccessMsg(`QR Code generated successfully! ID assigned: ${newRecord.sequence_number || newRecord.full_id}`);
      setShowCreateForm(false);
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || 'Failed to create QR code.');
    } finally {
      setCreating(false);
    }
  };

  // Single QR PNG Download
  const downloadSingleQr = (qrItem) => {
    const link = document.createElement('a');
    link.href = qrItem.qrDataUrl;
    link.download = `QR_${selectedClient}_${qrItem.sequence_number || qrItem.full_id}.png`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // PDF Export for All Client QRs (Exact 3cm x 3cm QR Image + Cutout Box)
  const downloadAllQrsAsPdf = async () => {
    if (!qrList || qrList.length === 0) return;
    setGeneratingPdf(true);

    try {
      const doc = new jsPDF({
        orientation: 'portrait',
        unit: 'mm',
        format: 'a4'
      });

      const pageWidth = 210;  // A4 width in mm
      const pageHeight = 297; // A4 height in mm
      const marginX = 12;
      const marginY = 15;
      
      // 1. EXACT QR CODE SIZE: 3cm x 3cm (30mm x 30mm)
      const qrSize = 30;

      // 2. CUTOUT CARD SIZE: 3.6cm wide x 4.8cm high (Fits QR + text with breathing room)
      const cardWidth = 36;  
      const cardHeight = 48; 
      
      const gapX = 4; // Horizontal spacing between boxes
      const gapY = 4; // Vertical spacing between boxes

      // Grid: Fits 4 across (4 x 36mm = 144mm) and 5 down (5 x 48mm = 240mm) = 20 cutouts per page
      const cols = Math.floor((pageWidth - marginX * 2 + gapX) / (cardWidth + gapX)); 
      const rows = Math.floor((pageHeight - marginY * 2 - 15 + gapY) / (cardHeight + gapY)); 
      const itemsPerPage = cols * rows;

      // Document Header
      doc.setFontSize(14);
      doc.setFont('helvetica', 'bold');
      doc.text(`QR Codes - ${selectedClient.toUpperCase()}`, marginX, marginY);
      doc.setFontSize(8);
      doc.setFont('helvetica', 'normal');
      doc.setTextColor(100);
      doc.text(`Generated on: ${new Date().toLocaleDateString()}`, marginX, marginY + 4);

      let startY = marginY + 10;

      for (let i = 0; i < qrList.length; i++) {
        const item = qrList[i];
        
        // Page break logic
        const pageItemIndex = i % itemsPerPage;
        if (i > 0 && pageItemIndex === 0) {
          doc.addPage();
          startY = marginY;
        }

        const colIndex = pageItemIndex % cols;
        const rowIndex = Math.floor(pageItemIndex / cols);

        // Coordinates for outer box
        const x = marginX + colIndex * (cardWidth + gapX);
        const y = startY + rowIndex * (cardHeight + gapY);

        // A. Draw Dotted Outer Cutout Box
        doc.setLineWidth(0.3);
        doc.setDrawColor(150, 150, 150);
        doc.setLineDashPattern([2, 2], 0);
        doc.rect(x, y, cardWidth, cardHeight);
        doc.setLineDashPattern([], 0); // Reset dash style

        // B. Add QR Image (Exact 3cm x 3cm) centered horizontally
        const qrX = x + (cardWidth - qrSize) / 2;
        const qrY = y + 3; // 3mm top padding inside box
        doc.addImage(item.qrDataUrl, 'PNG', qrX, qrY, qrSize, qrSize);

        // C. Room / Name Label
        doc.setFontSize(8);
        doc.setFont('helvetica', 'bold');
        doc.setTextColor(30, 41, 59);
        const displayName = item.name ? `${item.name}` : `Rm ${item.room_number}`;
        doc.text(displayName, x + cardWidth / 2, qrY + qrSize + 4.5, { align: 'center', maxWidth: cardWidth - 4 });

        // D. Sequential ID Label
        doc.setFontSize(9);
        doc.setFont('helvetica', 'bold');
        doc.setTextColor(37, 99, 235);
        doc.text(`ID: ${item.sequence_number || item.full_id}`, x + cardWidth / 2, qrY + qrSize + 9.5, { align: 'center' });
      }

      doc.save(`${selectedClient}_3cm_qrcodes.pdf`);
    } catch (err) {
      console.error('PDF generation error:', err);
      setErrorMsg('Failed to generate PDF document.');
    } finally {
      setGeneratingPdf(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 p-6 sm:p-10 font-sans">
      <div className="max-w-5xl mx-auto space-y-6">
        
        {/* Top Title Bar & Client Selection */}
        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
                <QrCode className="w-7 h-7 text-blue-600" />
                Feedback QR Code Manager
              </h1>
            </div>

            {/* Client Selection Dropdown & Add Client Trigger */}
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-2">
                <label className="text-xs font-semibold uppercase tracking-wider text-slate-500 flex items-center gap-1">
                  <Building2 className="w-4 h-4" /> Client:
                </label>
                {loadingClients ? (
                  <RefreshCw className="w-4 h-4 animate-spin text-blue-600" />
                ) : (
                  <select
                    value={selectedClient}
                    onChange={(e) => setSelectedClient(e.target.value)}
                    className="bg-slate-50 border border-slate-300 text-slate-800 font-semibold text-sm rounded-xl px-4 py-2 outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-600 transition"
                  >
                    {clients.map((col) => (
                      <option key={col} value={col}>
                        {col.toUpperCase()}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              {/* Add Client Button */}
              <button
                onClick={() => setShowAddClient(!showAddClient)}
                className="p-2 bg-slate-100 text-slate-700 rounded-xl hover:bg-slate-200 transition flex items-center gap-1 text-xs font-semibold"
                title="Add New Client Collection"
              >
                <UserPlus className="w-4 h-4 text-blue-600" />
                <span className="hidden sm:inline">Add Client</span>
              </button>
            </div>
          </div>

          {/* Inline Add Client Input Form */}
          {showAddClient && (
            <form onSubmit={handleAddClient} className="pt-3 border-t border-slate-100 flex items-center gap-3">
              <input
                type="text"
                placeholder="Enter new client name (e.g. Marriott)"
                value={newClientName}
                onChange={(e) => setNewClientName(e.target.value)}
                className="flex-1 bg-slate-50 border border-slate-300 rounded-xl px-3.5 py-1.5 text-sm outline-none focus:border-blue-600"
              />
              <button
                type="submit"
                disabled={addingClient}
                className="px-4 py-1.5 bg-blue-600 text-white text-xs font-semibold rounded-xl hover:bg-blue-700 transition flex items-center gap-1 disabled:bg-slate-300"
              >
                {addingClient && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                {addingClient ? 'Creating...' : 'Save Client'}
              </button>
            </form>
          )}
        </div>

        {/* Notifications (Auto-fading) */}
        {errorMsg && (
          <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-600 text-sm flex items-center gap-2 animate-fade-in">
            <AlertCircle className="w-5 h-5 shrink-0" />
            {errorMsg}
          </div>
        )}

        {successMsg && (
          <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-xl text-emerald-700 text-sm flex items-center gap-2 animate-fade-in">
            <CheckCircle2 className="w-5 h-5 shrink-0" />
            {successMsg}
          </div>
        )}

        {/* Action Header & Seamless Create Form */}
        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
            <h2 className="text-lg font-bold text-slate-900">
              QR Codes for <span className="text-blue-600 uppercase">{selectedClient || 'Select Client'}</span>
            </h2>
            
            <div className="flex items-center gap-2">
              <button
                onClick={downloadAllQrsAsPdf}
                disabled={!selectedClient || qrList.length === 0 || generatingPdf}
                className="px-4 py-2 bg-slate-800 text-white text-xs font-semibold rounded-xl hover:bg-slate-900 transition flex items-center gap-1.5 shadow-sm disabled:bg-slate-300"
                title="Download printable cut-out PDF sheet"
              >
                {generatingPdf ? <RefreshCw className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4 text-emerald-400" />}
                {generatingPdf ? 'Building PDF...' : 'Export To PDF'}
              </button>

              <button
                onClick={() => setShowCreateForm(!showCreateForm)}
                disabled={!selectedClient}
                className="px-4 py-2 bg-blue-600 text-white text-xs font-semibold rounded-xl hover:bg-blue-700 transition flex items-center gap-1.5 shadow-sm disabled:bg-slate-300"
              >
                <Plus className="w-4 h-4" />
                {showCreateForm ? 'Cancel' : 'Create New QR Code'}
              </button>
            </div>
          </div>

          {/* Inline Form */}
          {showCreateForm && (
            <form onSubmit={handleCreateQr} className="pt-4 border-t border-slate-100 grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-500 uppercase mb-1">Name</label>
                <input
                  type="text"
                  name="name"
                  placeholder="e.g. VIP Desk"
                  value={formData.name}
                  onChange={handleInputChange}
                  className="w-full bg-slate-50 border border-slate-300 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-500 uppercase mb-1">Room Number</label>
                <input
                  type="text"
                  name="room_number"
                  placeholder="e.g. 1004"
                  value={formData.room_number}
                  onChange={handleInputChange}
                  className="w-full bg-slate-50 border border-slate-300 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-500 uppercase mb-1"> ID </label>
                <input
                  type="text"
                  name="user_id"
                  placeholder="e.g. hyatt-suite"
                  value={formData.user_id}
                  onChange={handleInputChange}
                  className="w-full bg-slate-50 border border-slate-300 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600 font-mono"
                />
              </div>

              <div className="sm:col-span-3 flex justify-end">
                <button
                  type="submit"
                  disabled={creating}
                  className="px-6 py-2.5 bg-emerald-600 text-white font-semibold text-xs rounded-xl hover:bg-emerald-700 transition flex items-center gap-2 shadow-sm disabled:bg-slate-300"
                >
                  {creating && <RefreshCw className="w-4 h-4 animate-spin" />}
                  {creating ? 'Saving to DataCube...' : 'Generate QR Code'}
                </button>
              </div>
            </form>
          )}
        </div>

        {/* QR List Section */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          {loadingQrs ? (
            <div className="p-12 text-center text-slate-400 flex items-center justify-center gap-2">
              <RefreshCw className="w-5 h-5 animate-spin text-blue-600" />
              Loading client QR codes...
            </div>
          ) : qrList.length === 0 ? (
            <div className="p-12 text-center text-slate-400">
              No QR codes found in <span className="font-semibold">{selectedClient}</span> collection. Click above to create one.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50 border-b border-slate-200 text-xs text-slate-500 uppercase font-semibold">
                  <tr>
                    <th className="py-3 px-4">QR</th>
                    <th className="py-3 px-4">Name</th>
                    <th className="py-3 px-4">Room No.</th>
                    <th className="py-3 px-4">Link</th>
                    <th className="py-3 px-4 text-right">Download</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {qrList.map((qr, idx) => (
                    <tr key={qr.full_id || idx} className="hover:bg-slate-50 transition">
                      <td className="py-3 px-4">
                        {qr.qrDataUrl && (
                          <img
                            src={qr.qrDataUrl}
                            alt="QR"
                            className="w-12 h-12 rounded border border-slate-200 p-0.5 cursor-pointer hover:scale-105 transition"
                            onClick={() => setActiveQrImage(qr.qrDataUrl)}
                          />
                        )}
                      </td>
                      <td className="py-3 px-4 font-medium text-slate-800">{qr.name}</td>
                      <td className="py-3 px-4 text-slate-600">{qr.room_number}</td>
                      <td className="py-3 px-4">
                        <a
                          href={qr.target_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-xs text-slate-500 hover:text-blue-600 flex items-center gap-1 font-mono truncate max-w-xs"
                        >
                          <LinkIcon className="w-3 h-3 shrink-0" />
                          {qr.target_url}
                        </a>
                      </td>
                      <td className="py-3 px-4 text-right">
                        <button
                          onClick={() => downloadSingleQr(qr)}
                          className="p-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold inline-flex items-center gap-1 transition"
                          title="Download PNG QR Code"
                        >
                          <Download className="w-3.5 h-3.5 text-blue-600" />
                          <span className="hidden sm:inline">PNG</span>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}