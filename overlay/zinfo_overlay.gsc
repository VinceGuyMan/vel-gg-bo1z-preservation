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

	while ( !IsDefined( get_players() ) || get_players().size == 0 )
	{
		wait( 0.1 );
	}

	label_zombies = zinfo_hud_elem( 6, 52, 1.25 );
	label_zombies SetText( "zombies alive:" );
	label_zombies.color = ( 1.0, 0.35, 0.35 );

	val_alive = zinfo_hud_elem( 96, 52, 1.25 );
	val_alive.color = ( 1.0, 1.0, 1.0 );

	label_left = zinfo_hud_elem( 6, 68, 1.15 );
	label_left SetText( "left this round:" );
	label_left.color = ( 0.85, 0.85, 0.85 );

	val_left = zinfo_hud_elem( 102, 68, 1.15 );
	val_left.color = ( 1.0, 0.85, 0.25 );

	label_wave = zinfo_hud_elem( 6, 84, 1.15 );
	label_wave SetText( "round:" );
	label_wave.color = ( 0.85, 0.85, 0.85 );

	val_wave = zinfo_hud_elem( 52, 84, 1.15 );
	val_wave.color = ( 1.0, 0.85, 0.25 );

	last_alive = -1;
	last_left = -1;
	last_round = -1;
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
		label_left.alpha = a;
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

		if ( on != last_on || ( on && ( alive != last_alive || left != last_left || cur_round != last_round || GetTime() - last_send >= 3000 ) ) )
		{
			players = get_players();
			for ( i = 0; i < players.size; i++ )
			{
				players[i] SetClientDvars( "kisak_mod_tabinfo", on, "zinfo_alive", alive, "zinfo_left", left );
			}
			last_on = on;
			last_alive = alive;
			last_left = left;
			last_round = cur_round;
			last_send = GetTime();
		}
		wait( 0.2 );
	}
}
