import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { toast } from "sonner";
import { ArrowLeft, UserPlus, Trash2, RefreshCw, Smartphone, Check, X, Clock } from "lucide-react";
import api from "../lib/api";

const API = process.env.REACT_APP_BACKEND_URL;
const FAKE_EMAIL_DOMAIN = "@alphasignal.local";

// Cria login com usuário simples (sem parecer e-mail) OU e-mail de verdade,
// se quiser cadastrar alguém assim também. Mesma lógica do Login.js.
function toSupabaseIdentifier(input) {
  const trimmed = input.trim();
  if (trimmed.includes("@")) return trimmed;
  return `${trimmed.toLowerCase()}${FAKE_EMAIL_DOMAIN}`;
}

// Pra exibição: se for um dos e-mails disfarçados, mostra só o usuário
// (sem o @alphasignal.local feio). Se for um e-mail de verdade, mostra normal.
function displayIdentifier(email) {
  if (email && email.endsWith(FAKE_EMAIL_DOMAIN)) {
    return email.slice(0, -FAKE_EMAIL_DOMAIN.length);
  }
  return email;
}

// ============================================================
// Painel de dispositivos de um usuário — expande dentro da linha dele
// ============================================================
const DevicesPanel = ({ userId }) => {
  const [loading, setLoading] = useState(true);
  const [devices, setDevices] = useState([]);
  const [maxDevices, setMaxDevices] = useState(1);
  const [savingLimit, setSavingLimit] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get(`${API}/api/admin/users/${userId}/devices`);
      setDevices(res.data.devices || []);
      setMaxDevices(res.data.max_devices || 1);
    } catch (error) {
      toast.error("Erro ao carregar dispositivos");
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => { load(); }, [load]);

  const handleSaveLimit = async () => {
    setSavingLimit(true);
    try {
      await api.post(`${API}/api/admin/users/${userId}/max-devices`, { max_devices: maxDevices });
      toast.success("Limite atualizado");
    } catch (error) {
      toast.error("Erro ao salvar limite");
    } finally {
      setSavingLimit(false);
    }
  };

  const handleRemoveDevice = async (deviceId) => {
    try {
      await api.delete(`${API}/api/admin/users/${userId}/devices/${deviceId}`);
      toast.success("Dispositivo removido — libera espaço pra outro");
      load();
    } catch (error) {
      toast.error("Erro ao remover dispositivo");
    }
  };

  return (
    <div className="mt-2 mb-3 ml-2 pl-3 border-l-2 border-white/10 space-y-2" data-testid={`devices-panel-${userId}`}>
      <div className="flex items-center gap-2">
        <Label className="text-xs text-muted-foreground">Limite de dispositivos:</Label>
        <Input
          type="number"
          min={1}
          max={10}
          value={maxDevices}
          onChange={(e) => setMaxDevices(parseInt(e.target.value, 10) || 1)}
          className="bg-surface border-white/10 text-white h-7 w-16 text-xs"
        />
        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={handleSaveLimit} disabled={savingLimit}>
          Salvar
        </Button>
      </div>

      {loading ? (
        <p className="text-xs text-muted-foreground">Carregando dispositivos...</p>
      ) : devices.length === 0 ? (
        <p className="text-xs text-muted-foreground">Nenhum dispositivo registrado ainda.</p>
      ) : (
        <div className="space-y-1">
          {devices.map((d) => (
            <div key={d} className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground font-mono truncate max-w-[200px]">{d}</span>
              <button onClick={() => handleRemoveDevice(d)} className="text-banker hover:text-banker/70">
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}
      <p className="text-[10px] text-muted-foreground">
        {devices.length}/{maxDevices} dispositivo(s) em uso
      </p>
    </div>
  );
};

export default function AdminPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [creating, setCreating] = useState(false);
  const [users, setUsers] = useState([]);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [deletingId, setDeletingId] = useState(null);
  const [forbidden, setForbidden] = useState(false);
  const [expandedDevicesFor, setExpandedDevicesFor] = useState(null);

  const [pending, setPending] = useState([]);
  const [loadingPending, setLoadingPending] = useState(true);
  const [decidingId, setDecidingId] = useState(null);

  const loadUsers = useCallback(async () => {
    setLoadingUsers(true);
    try {
      const res = await api.get(`${API}/api/admin/users`);
      setUsers(res.data.users || []);
      setForbidden(false);
    } catch (error) {
      if (error?.response?.status === 403) {
        setForbidden(true);
      } else {
        toast.error("Erro ao carregar usuários");
      }
    } finally {
      setLoadingUsers(false);
    }
  }, []);

  const loadPending = useCallback(async () => {
    setLoadingPending(true);
    try {
      const res = await api.get(`${API}/api/admin/pending-signups`);
      setPending(res.data.pending || []);
    } catch (error) {
      // se já deu forbidden no loadUsers, não precisa duplicar o erro aqui
    } finally {
      setLoadingPending(false);
    }
  }, []);

  useEffect(() => {
    loadUsers();
    loadPending();
  }, [loadUsers, loadPending]);

  const handleCreate = async (e) => {
    e.preventDefault();
    setCreating(true);
    try {
      const email = toSupabaseIdentifier(username);
      await api.post(`${API}/api/admin/users`, { email, password });
      toast.success(`Login criado: ${username}`);
      setUsername("");
      setPassword("");
      loadUsers();
    } catch (error) {
      const msg = error?.response?.data?.detail || "Erro ao criar usuário";
      toast.error(msg);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (userId, userEmail) => {
    if (!window.confirm(`Remover o acesso de ${displayIdentifier(userEmail)}? Essa ação não pode ser desfeita.`)) return;
    setDeletingId(userId);
    try {
      await api.delete(`${API}/api/admin/users/${userId}`);
      toast.success("Usuário removido");
      loadUsers();
    } catch (error) {
      toast.error("Erro ao remover usuário");
    } finally {
      setDeletingId(null);
    }
  };

  const handleApprove = async (pendingId, pendingUsername) => {
    setDecidingId(pendingId);
    try {
      await api.post(`${API}/api/admin/pending-signups/${pendingId}/approve`);
      toast.success(`Aprovado: ${pendingUsername}`);
      loadPending();
      loadUsers();
    } catch (error) {
      const msg = error?.response?.data?.detail || "Erro ao aprovar";
      toast.error(msg);
    } finally {
      setDecidingId(null);
    }
  };

  const handleReject = async (pendingId) => {
    setDecidingId(pendingId);
    try {
      await api.post(`${API}/api/admin/pending-signups/${pendingId}/reject`);
      toast.success("Pedido rejeitado");
      loadPending();
    } catch (error) {
      toast.error("Erro ao rejeitar");
    } finally {
      setDecidingId(null);
    }
  };

  if (forbidden) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#14171c] p-4">
        <div className="glass rounded-lg p-8 max-w-md text-center">
          <p className="text-banker font-semibold mb-2">Acesso restrito</p>
          <p className="text-sm text-muted-foreground mb-4">Essa área é só para o administrador.</p>
          <Button variant="outline" onClick={() => navigate("/")}>Voltar</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#14171c] p-4">
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center gap-3 mb-6">
          <Button variant="ghost" size="icon" onClick={() => navigate("/")} data-testid="admin-back-btn">
            <ArrowLeft className="w-5 h-5" />
          </Button>
          <h1 className="font-heading font-bold text-xl text-white">Painel de Administração</h1>
        </div>

        {/* Pedidos pendentes */}
        {pending.length > 0 && (
          <div className="glass rounded-lg p-6 mb-6 border border-tie/40" data-testid="admin-pending-list">
            <h2 className="font-heading font-semibold text-white mb-3 flex items-center gap-2">
              <Clock className="w-4 h-4 text-tie" />
              Pedidos pendentes ({pending.length})
            </h2>
            <div className="space-y-2">
              {pending.map((p) => (
                <div key={p.id} className="flex items-center justify-between py-2 border-b border-white/5 last:border-0">
                  <div>
                    <p className="text-sm text-white">{p.username}</p>
                    <p className="text-xs text-muted-foreground">
                      {new Date(p.created_at).toLocaleString("pt-BR")}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      className="h-8 bg-green-500 text-black hover:bg-green-400"
                      onClick={() => handleApprove(p.id, p.username)}
                      disabled={decidingId === p.id}
                      data-testid={`approve-${p.id}`}
                    >
                      <Check className="w-3 h-3 mr-1" /> Aprovar
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-8 text-banker border-banker/40 hover:bg-banker/10"
                      onClick={() => handleReject(p.id)}
                      disabled={decidingId === p.id}
                      data-testid={`reject-${p.id}`}
                    >
                      <X className="w-3 h-3 mr-1" /> Rejeitar
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Criar novo login */}
        <div className="glass rounded-lg p-6 mb-6" data-testid="admin-create-form">
          <h2 className="font-heading font-semibold text-white mb-1 flex items-center gap-2">
            <UserPlus className="w-4 h-4" />
            Criar login novo
          </h2>
          <p className="text-xs text-muted-foreground mb-4">
            Funciona automaticamente no AlphaSignal e no MetaEdge — é o mesmo login pros dois.
          </p>
          <form onSubmit={handleCreate} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="new-username" className="text-white">Usuário do cliente</Label>
              <Input
                id="new-username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="joao123"
                className="bg-surface border-white/10 text-white"
                required
                data-testid="admin-new-email"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-password" className="text-white">Senha</Label>
              <Input
                id="new-password"
                type="text"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Mínimo 6 caracteres"
                className="bg-surface border-white/10 text-white"
                required
                minLength={6}
                data-testid="admin-new-password"
              />
            </div>
            <Button
              type="submit"
              disabled={creating}
              className="w-full bg-player text-black hover:bg-player/90 font-semibold"
              data-testid="admin-create-submit"
            >
              {creating ? "Criando..." : "Criar login"}
            </Button>
          </form>
        </div>

        {/* Lista de usuários */}
        <div className="glass rounded-lg p-6" data-testid="admin-users-list">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-heading font-semibold text-white">Clientes cadastrados</h2>
            <Button variant="ghost" size="icon" onClick={loadUsers} title="Recarregar">
              <RefreshCw className="w-4 h-4" />
            </Button>
          </div>

          {loadingUsers ? (
            <p className="text-sm text-muted-foreground">Carregando...</p>
          ) : users.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhum usuário encontrado.</p>
          ) : (
            <div className="space-y-1">
              {users.map((u) => (
                <div key={u.id}>
                  <div
                    className="flex items-center justify-between py-2 border-b border-white/5 last:border-0"
                    data-testid={`admin-user-row-${u.id}`}
                  >
                    <div>
                      <p className="text-sm text-white">{displayIdentifier(u.email)}</p>
                      <p className="text-xs text-muted-foreground">
                        {u.last_sign_in_at ? `Último acesso: ${new Date(u.last_sign_in_at).toLocaleDateString("pt-BR")}` : "Nunca logou"}
                      </p>
                    </div>
                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setExpandedDevicesFor(expandedDevicesFor === u.id ? null : u.id)}
                        className="text-muted-foreground hover:text-player"
                        title="Dispositivos"
                        data-testid={`admin-devices-btn-${u.id}`}
                      >
                        <Smartphone className="w-4 h-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => handleDelete(u.id, u.email)}
                        disabled={deletingId === u.id}
                        className="text-muted-foreground hover:text-banker"
                        data-testid={`admin-delete-${u.id}`}
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                  {expandedDevicesFor === u.id && <DevicesPanel userId={u.id} />}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
