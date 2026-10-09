  (func $Coop_ParseIPv4 (param $text i32) (param $addr i32) (result i32)
    (local $octet i32) (local $value i32) (local $digits i32) (local $ch i32) (local $port i32)
    local.get $addr i32.const 0 i32.const 16 memory.fill
    loop $octets
      i32.const 0 local.set $value
      i32.const 0 local.set $digits
      block $endDigits
        loop $digitsLoop
          local.get $text i32.load8_u local.tee $ch
          i32.const 48 i32.lt_u br_if $endDigits
          local.get $ch i32.const 57 i32.gt_u br_if $endDigits
          local.get $value i32.const 10 i32.mul
          local.get $ch i32.const 48 i32.sub i32.add local.tee $value
          i32.const 255 i32.gt_u if i32.const 0 return end
          local.get $digits i32.const 1 i32.add local.set $digits
          local.get $text i32.const 1 i32.add local.set $text
          br $digitsLoop
        end
      end
      local.get $digits i32.eqz if i32.const 0 return end
      local.get $addr i32.const 4 i32.add local.get $octet i32.add
      local.get $value i32.store8
      local.get $octet i32.const 1 i32.add local.tee $octet
      i32.const 4 i32.lt_u
      if
        local.get $ch i32.const 46 i32.ne if i32.const 0 return end
        local.get $text i32.const 1 i32.add local.set $text
        br $octets
      end
    end
    i32.const 3074 local.set $port
    local.get $ch i32.const 58 i32.eq
    if
      local.get $text i32.const 1 i32.add local.set $text
      i32.const 0 local.set $port
      i32.const 0 local.set $digits
      block $endPort
        loop $portLoop
          local.get $text i32.load8_u local.tee $ch
          i32.const 48 i32.lt_u br_if $endPort
          local.get $ch i32.const 57 i32.gt_u br_if $endPort
          local.get $port i32.const 10 i32.mul
          local.get $ch i32.const 48 i32.sub i32.add local.tee $port
          i32.const 65535 i32.gt_u if i32.const 0 return end
          local.get $digits i32.const 1 i32.add local.set $digits
          local.get $text i32.const 1 i32.add local.set $text
          br $portLoop
        end
      end
      local.get $digits i32.eqz if i32.const 0 return end
      local.get $port i32.eqz if i32.const 0 return end
    end
    local.get $ch if i32.const 0 return end
    local.get $addr i32.const 4 i32.store
    local.get $addr local.get $port i32.const 8 i32.shl
    local.get $port i32.const 8 i32.shr_u i32.or i32.store16 offset=8
    i32.const 1)

  (func $Coop_IsLAN (param $addr i32) (result i32)
    (local $first i32) (local $second i32)
    local.get $addr i32.load i32.const 2 i32.eq if i32.const 1 return end
    local.get $addr i32.load i32.const 4 i32.ne if i32.const 0 return end
    local.get $addr i32.load8_u offset=4 local.set $first
    local.get $addr i32.load8_u offset=5 local.set $second
    local.get $first i32.const 10 i32.eq
    local.get $first i32.const 127 i32.eq i32.or
    if i32.const 1 return end
    local.get $first i32.const 192 i32.eq
    local.get $second i32.const 168 i32.eq i32.and
    if i32.const 1 return end
    local.get $first i32.const 172 i32.eq
    local.get $second i32.const 16 i32.ge_u i32.and
    local.get $second i32.const 31 i32.le_u i32.and)

  ;; For an explicitly configured Zombies/LAN room, before initial gamestate.
  ;; This retains the original auth branches and never alters loopback hosts.
  (func $Coop_PrepareZombiesLAN (param $addr i32)
    (local $boot i32) (local $mode i32) (local $state i32)
    i32.const 184721744 i32.atomic.load local.tee $state
    if local.get $state i32.const 1 i32.atomic.rmw.add offset=52 drop end
    local.get $addr
    i32.load
    i32.const 4
    i32.ne
    if return end
    local.get $addr
    call $Coop_IsLAN
    i32.eqz
    if return end
    i32.const 134904788
    i32.load
    local.tee $boot
    i32.eqz
    if return end
    local.get $boot
    i32.load8_u offset=24
    i32.const 1
    i32.ne
    if return end
    i32.const 134904784
    i32.load
    local.tee $mode
    i32.eqz
    if return end
    local.get $state if local.get $state local.get $mode i32.load8_u offset=24 i32.store offset=56 end
    local.get $mode
    i32.const 1
    i32.const 0
    call $Dvar_SetBoolFromSource_dvar_s*__bool__DvarSetSource_
    local.get $state if local.get $state local.get $mode i32.load8_u offset=24 i32.store offset=60 end)


  ;; Complete the existing warm client restart after it enters CS_PRIMED.
  ;; This matches the ordinary full-client initialization's loading completion.
  ;; Retain the original restart, snapshots, asserts and gameplay scripts.
  (func $Coop_FinishWarmRemote (param $localClient i32)
    (local $dvar i32) (local $connection i32)
    local.get $localClient if return end
    i32.const 134904784 i32.load local.tee $dvar i32.eqz if return end
    local.get $dvar i32.load8_u offset=24 i32.eqz if return end
    i32.const 134904788 i32.load local.tee $dvar i32.eqz if return end
    local.get $dvar i32.load8_u offset=24 i32.eqz if return end
    i32.const 13391960 i32.load i32.const 9 i32.ne if return end
    local.get $localClient call $CL_GetLocalClientConnection_int_ local.set $connection
    local.get $connection i32.load offset=16 i32.const 4 i32.ne if return end
    local.get $connection i32.const 16 i32.add call $Coop_IsLAN i32.eqz if return end
    i32.const 43783024 i32.const 0 i32.store8)

  ;; main's startup menu used to reset a pending remote Zombies connection.
  ;; Normal menu/error/leave paths retain their original implementation.
  (func $Coop_StartupFrontEnd
    (local $boot i32) (local $connection i32)
    block $load
      i32.const 13391960 i32.load i32.const 4 i32.lt_u br_if $load
      i32.const 134904788 i32.load local.tee $boot i32.eqz br_if $load
      local.get $boot i32.load8_u offset=24 i32.const 1 i32.ne br_if $load
      i32.const 43783020 i32.load local.tee $connection i32.eqz br_if $load
      local.get $connection i32.load offset=16 i32.const 4 i32.ne br_if $load
      local.get $connection i32.const 16 i32.add call $Coop_IsLAN i32.eqz br_if $load
      return
    end
    call $Com_LoadFrontEnd__)

  (func $Coop_Send (param $sock i32) (param $length i32) (param $data i32) (param $to i32) (result i32)
    (local $state i32) (local $write i32) (local $slot i32)
    i32.const 184721744 i32.atomic.load local.tee $state
    i32.eqz if i32.const 0 return end
    local.get $to i32.load i32.const 4 i32.ne if i32.const 0 return end
    local.get $length i32.const 65536 i32.gt_u if
      local.get $state i32.const 1 i32.atomic.rmw.add offset=16 drop
      i32.const 0 return
    end
    loop $lock
      local.get $state i32.const 0 i32.const 1 i32.atomic.rmw.cmpxchg offset=20
      br_if $lock
    end
    local.get $state i32.atomic.load offset=8 local.set $write
    local.get $write local.get $state i32.atomic.load offset=12 i32.sub
    i32.const 32 i32.ge_u
    if
      local.get $state i32.const 1 i32.atomic.rmw.add offset=16 drop
      local.get $state i32.const 0 i32.atomic.store offset=20
      i32.const 0 return
    end
    local.get $state i32.const 64 i32.add
    local.get $write i32.const 31 i32.and i32.const 65568 i32.mul i32.add local.set $slot
    local.get $slot local.get $sock i32.store
    local.get $slot local.get $length i32.store offset=4
    local.get $slot i32.const 8 i32.add local.get $to i32.const 16 memory.copy
    local.get $slot i32.const 24 i32.add local.get $data local.get $length memory.copy
    local.get $state local.get $write i32.const 1 i32.add i32.atomic.store offset=8
    local.get $state i32.const 0 i32.atomic.store offset=20
    i32.const 1)

  (func $Coop_Receive (param $sock i32) (param $from i32) (param $msg i32) (result i32)
    (local $state i32) (local $head i32) (local $read i32) (local $slot i32) (local $length i32)
    i32.const 184721744 i32.atomic.load local.tee $state
    i32.eqz if i32.const 0 return end
    local.get $sock i32.eqz
    if
      local.get $state i32.atomic.load offset=48 i32.const 1 i32.eq
      if
        i32.const 0 local.get $state i32.const 6294592 i32.add
        call $Cbuf_AddText_int__char_const*_
        local.get $state i32.const 0 i32.atomic.store offset=48
      end
    end
    local.get $sock i32.const 1 i32.gt_u if i32.const 0 return end
    local.get $state i32.const 24 i32.add local.get $sock i32.const 12 i32.mul i32.add local.set $head
    local.get $head i32.atomic.load offset=4 local.set $read
    local.get $read local.get $head i32.atomic.load i32.eq if i32.const 0 return end
    local.get $state i32.const 2098240 i32.add
    local.get $sock i32.const 2098176 i32.mul i32.add
    local.get $read i32.const 31 i32.and i32.const 65568 i32.mul i32.add local.set $slot
    local.get $slot i32.load offset=4 local.set $length
    local.get $length i32.const 65536 i32.gt_u
    local.get $length local.get $msg i32.load offset=16 i32.gt_u i32.or
    if
      local.get $head i32.const 1 i32.atomic.rmw.add offset=8 drop
      local.get $head local.get $read i32.const 1 i32.add i32.atomic.store offset=4
      i32.const 0 return
    end
    local.get $from local.get $slot i32.const 8 i32.add i32.const 16 memory.copy
    local.get $msg i32.load offset=8 local.get $slot i32.const 24 i32.add local.get $length memory.copy
    local.get $msg local.get $length i32.store offset=20
    local.get $head local.get $read i32.const 1 i32.add i32.atomic.store offset=4
    i32.const 1)
  (export "Coop_ParseIPv4" (func $Coop_ParseIPv4))
  (export "Coop_Send" (func $Coop_Send))
  (export "Coop_Receive" (func $Coop_Receive))
