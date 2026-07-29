import React, { useState, useEffect } from 'react';
import { Building2, QrCode, Plus, RefreshCw, CheckCircle2, AlertCircle, Link as LinkIcon, UserPlus } from 'lucide-react';
import QRCode from 'qrcode';
import axios from 'axios';

export default function FeedbackQrManager() {
  const [clients, setClients] = useState([]);
  const [selectedClient, setSelectedClient] = useState('');
  const [qrList, setQrList] = useState([]);
  
  // Loading & Toggle Flags
  const [loadingClients, setLoadingClients] = useState(true);
  const [loadingQrs, setLoadingQrs] = useState(false);
  const [creating, setCreating] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);
  
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

      // Generate QR Code image data URLs for display
      const processedQrs = await Promise.all(
        rawQrs.map(async (item) => {
          const qrDataUrl = await QRCode.toDataURL(item.target_url || `https://feedback?id=${item.full_id}`, { width: 150 });
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

      // Refresh clients dropdown and auto-select new client
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
      setErrorMsg('Please fill in all fields (Name, Room Number, Alphanumeric ID).');
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

      // Generate QR Image for the new item
      const qrDataUrl = await QRCode.toDataURL(newRecord.target_url, { width: 150 });
      const fullRecord = { ...newRecord, qrDataUrl };

      // Update frontend list seamlessly
      setQrList((prev) => [fullRecord, ...prev]);

      // Reset Form & show success notice
      setFormData({ name: '', room_number: '', user_id: '' });
      setSuccessMsg(`QR Code generated successfully! ID assigned: ${newRecord.full_id}`);
      setShowCreateForm(false);
    } catch (err) {
      setErrorMsg(err.response?.data?.detail || 'Failed to create QR code.');
    } finally {
      setCreating(false);
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
              <p className="text-xs text-slate-500 mt-1">
                DataCube Database: <code className="bg-slate-100 px-1 py-0.5 rounded font-mono text-blue-600">feedback_qr</code>
              </p>
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

        {/* Notifications */}
        {errorMsg && (
          <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-600 text-sm flex items-center gap-2">
            <AlertCircle className="w-5 h-5 shrink-0" />
            {errorMsg}
          </div>
        )}

        {successMsg && (
          <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-xl text-emerald-700 text-sm flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 shrink-0" />
            {successMsg}
          </div>
        )}

        {/* Action Header & Seamless Create Form */}
        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
          <div className="flex justify-between items-center">
            <h2 className="text-lg font-bold text-slate-900">
              QR Codes for <span className="text-blue-600 uppercase">{selectedClient || 'Select Client'}</span>
            </h2>
            <button
              onClick={() => setShowCreateForm(!showCreateForm)}
              disabled={!selectedClient}
              className="px-4 py-2 bg-blue-600 text-white text-xs font-semibold rounded-xl hover:bg-blue-700 transition flex items-center gap-1.5 shadow-sm disabled:bg-slate-300"
            >
              <Plus className="w-4 h-4" />
              {showCreateForm ? 'Cancel' : 'Create New QR Code'}
            </button>
          </div>

          {/* Inline Seamless Form */}
          {showCreateForm && (
            <form onSubmit={handleCreateQr} className="pt-4 border-t border-slate-100 grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-500 uppercase mb-1">Name / Tag</label>
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
                <label className="block text-xs font-medium text-slate-500 uppercase mb-1">Room / Location Number</label>
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
                <label className="block text-xs font-medium text-slate-500 uppercase mb-1">Alphanumeric ID Prefix</label>
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
                  {creating ? 'Saving to DataCube...' : 'Generate & Save QR'}
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
                    <th className="py-3 px-4">Full Generated ID</th>
                    <th className="py-3 px-4">Name</th>
                    <th className="py-3 px-4">Room No.</th>
                    <th className="py-3 px-4">Target Link</th>
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
                      <td className="py-3 px-4 font-mono font-bold text-blue-600">
                        {qr.full_id}
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