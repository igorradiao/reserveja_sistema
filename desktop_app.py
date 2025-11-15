import tkinter as tk
from tkinter import ttk
import sqlite3
from datetime import datetime

DB = "sala_agenda.db"

def carregar_ambientes():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, nome FROM ambientes")
    dados = cur.fetchall()
    conn.close()
    return dados

def buscar_agenda():
    amb_id = var_ambiente.get()
    if not amb_id:
        return

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    hoje = datetime.now().strftime("%Y-%m-%d")
    inicio = f"{hoje} 00:00:00"
    fim = f"{hoje} 23:59:59"

    cur.execute("""
        SELECT a.inicio, a.fim, u.nome
        FROM agendamentos a
        JOIN usuarios u ON u.id = a.usuario_id
        WHERE a.ambiente_id = ?
        AND a.inicio BETWEEN ? AND ?
        ORDER BY a.inicio
    """, (amb_id, inicio, fim))

    linhas = cur.fetchall()
    conn.close()

    texto.delete("1.0", tk.END)
    if not linhas:
        texto.insert(tk.END, "Nenhum agendamento hoje.\n")
        return

    for ini, fim, nome in linhas:
        texto.insert(tk.END, f"{ini} - {fim} | {nome}\n")

root = tk.Tk()
root.title("Agenda de Ambientes (Desktop)")

frame = ttk.Frame(root, padding=10)
frame.pack()

ttk.Label(frame, text="Ambiente:").pack()

var_ambiente = tk.StringVar()
cb = ttk.Combobox(frame, textvariable=var_ambiente)

ambs = carregar_ambientes()
cb["values"] = [str(a[0]) + " - " + a[1] for a in ambs]
cb.pack()

ttk.Button(frame, text="Ver Agenda de Hoje", command=buscar_agenda).pack(pady=10)

texto = tk.Text(root, width=60, height=15)
texto.pack()

root.mainloop()
