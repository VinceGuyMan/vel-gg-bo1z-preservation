#include maps\_utility;
#include common_scripts\utility;
#include maps\_zombiemode_utility;

zinfo_hud_elem( x, y, fontScale )
{
	hud = NewHudElem();
	hud.alignX = "left";
	hud.alignY = "top";
	hud.horzAlign = "left";
	hud.vertAlign = "top";
	hud.x = x;
	hud.y = y;
	hud.fontScale = fontScale;
	hud.foreground = true;
	hud.hidewheninmenu = true;
	hud.alpha = 1;
	return hud;
}

main( default_on )
{
	if ( GetDvar( #"zinfo" ) == "" )
	{
		SetDvar( "zinfo", default_on );
	}
	flag_wait( "all_players_connected" );

	label_zombies = zinfo_hud_elem( 6, 52, 1.25 );
	label_zombies SetText( "Zombies:" );
	label_zombies.color = ( 1.0, 0.25, 0.25 );

	val_alive = zinfo_hud_elem( 70, 52, 1.25 );
	val_alive.color = ( 1.0, 1.0, 1.0 );

	label_slash = zinfo_hud_elem( 98, 52, 1.25 );
	label_slash SetText( "/" );
	label_slash.color = ( 0.65, 0.65, 0.65 );

	val_left = zinfo_hud_elem( 110, 52, 1.25 );
	val_left.color = ( 1.0, 0.85, 0.25 );

	label_wave = zinfo_hud_elem( 6, 70, 1.15 );
	label_wave SetText( "Round:" );
	label_wave.color = ( 0.8, 0.8, 0.8 );

	val_wave = zinfo_hud_elem( 56, 70, 1.15 );
	val_wave.color = ( 1.0, 1.0, 0.35 );

	last_alive = -1;
	last_left = -1;
	last_on = -1;
	last_send = 0;

	for ( ;; )
	{
		on = GetDvarInt( #"zinfo" ) != 0;
		a = 0;
		if ( on )
		{
			a = 1;
		}

		label_zombies.alpha = a;
		val_alive.alpha = a;
		label_slash.alpha = a;
		val_left.alpha = a;
		label_wave.alpha = a;
		val_wave.alpha = a;

		alive = get_enemy_count();
		left = alive;
		if ( IsDefined( level.zombie_total ) && level.zombie_total > 0 )
		{
			left += level.zombie_total;
		}

		cur_round = 1;
		if ( IsDefined( level.round_number ) )
		{
			cur_round = level.round_number;
		}

		if ( on )
		{
			val_alive SetValue( alive );
			val_left SetValue( left );
			val_wave SetValue( cur_round );
		}

		if ( on != last_on || ( on && ( alive != last_alive || left != last_left || GetTime() - last_send >= 5000 ) ) )
		{
			players = get_players();
			for ( i = 0; i < players.size; i++ )
			{
				players[i] SetClientDvars( "kisak_mod_tabinfo", on, "zinfo_alive", alive, "zinfo_left", left );
			}
			if ( on && ( alive != last_alive || left != last_left ) )
			{
				LogPrint( "zinfo: alive " + alive + " left " + left + " round " + cur_round + " t " + GetTime() + "\n" );
				PrintLn( "zinfo: alive " + alive + " left " + left + " round " + cur_round + " t " + GetTime() + "\n" );
			}
			last_on = on;
			last_alive = alive;
			last_left = left;
			last_send = GetTime();
		}
		wait( 0.25 );
	}
}
